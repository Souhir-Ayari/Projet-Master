"""
build_knowledge.py
--------------------
Orchestrateur OFFLINE du pipeline méthodologie/mitigation (Steps 1-5) :

    PDF -> texte -> chunks
       -> Layer 1 : extraction d'entités (existant, INCHANGÉ - main.py)
       -> Layer 2 : résumé attaque/mitigation ancré sur le texte + les
          entités Layer 1 (Step 1), catégorie MITRE validée (Step 2),
          mitigation structurée (type + résumé), conservée dès l'attaque
          confirmée (Step 3)
       -> score de généralisabilité (Step 4)
       -> knowledge_table.jsonl (Step 5), qui grossit avec chaque nouveau
          paper traité

Deux DOMAINES d'analyse, chacun avec sa taxonomie Layer 1, son prompt
spécialisé et son référentiel MITRE (voir --domain) :
  - "llm" (défaut)  : menaces émergentes sur les LLM, référentiel MITRE ATLAS
  - "supply_chain"  : compromissions de chaîne d'approvisionnement logicielle,
                      référentiel MITRE ATT&CK

À lancer UNE FOIS par paper du corpus (viser 15-30+ papers avant que le
retrieval, Step 6 - voir retrieval.py/query_knowledge.py - soit significatif).
Réutilise GLiNER/Mistral, ne les duplique pas.

Usage :
    python build_knowledge.py --pdf greshake_indirect_injection.pdf
    python build_knowledge.py --pdf backdoor.pdf --domain supply_chain
    python build_knowledge.py --pdf paper.pdf --table results/knowledge_table.jsonl

Plusieurs papers en un run (GLiNER et Mistral chargés une seule fois) : passer
plusieurs PDF ou un dossier. --skip-existing saute les papers déjà présents
dans la table, pour reprendre un lot interrompu sans tout refaire :
    python build_knowledge.py --pdf corpus_llm/ --table results/knowledge_table_llm.jsonl --skip-existing
"""

import argparse
import glob
import os
from collections import Counter

import attack_taxonomy
from config import DEFAULT_DOMAIN, KNOWLEDGE_TABLE_PATH, topic_config
from deduplication import MAX_CASES_PER_CATEGORY
from gliner_extractor import GLiNERExtractor
from jsonl_utils import clear_jsonl
from knowledge_table import build_table_from_methodology_records, load_table, vector_paths_for
from methodology_extractor import MethodologyExtractor
from mistral_extractor import MistralExtractor
from pdf_extractor import chunk_text, extract_text_from_pdf


def main():
    parser = argparse.ArgumentParser(
        description="Construit/complète la table de connaissance à partir d'UN paper (Steps 1-5)."
    )
    parser.add_argument(
        "--pdf",
        required=True,
        nargs="+",
        help="PDF(s) d'entrée, ou dossier(s) dont tous les .pdf sont traités",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Ne pas retraiter un paper déjà présent dans la table (même nom de "
        "fichier). Sans cette option, un paper déjà traité est REMPLACÉ.",
    )
    parser.add_argument(
        "--backend", default="ollama", choices=["ollama", "transformers"]
    )
    parser.add_argument(
        "--domain",
        default=DEFAULT_DOMAIN,
        choices=attack_taxonomy.available_domains(),
        help="Domaine d'analyse : 'llm' (menaces sur les LLM, référentiel MITRE "
        "ATLAS — défaut) ou 'supply_chain' (chaîne d'approvisionnement "
        "logicielle, référentiel MITRE ATT&CK). Détermine la taxonomie de "
        "labels Layer 1, le prompt de Layer 2 et le référentiel de validation.",
    )
    parser.add_argument(
        "--table",
        default=KNOWLEDGE_TABLE_PATH,
        help="Chemin de la table de connaissance JSONL (par défaut : "
        "config.KNOWLEDGE_TABLE_PATH). Les deux stores vectoriels suivent "
        "automatiquement le nom de la table (voir vector_paths_for) : un "
        "corpus = un triplet JSONL + 2 .npz, jamais mélangé avec un autre.",
    )
    parser.add_argument(
        "--max-per-category",
        type=int,
        default=MAX_CASES_PER_CATEGORY,
        help="Nombre maximum de cas gardés par catégorie MITRE POUR CE PAPIER "
        f"(défaut : {MAX_CASES_PER_CATEGORY}). Un papier de recherche reformule "
        "son sujet dans l'intro, le related work et la conclusion : sans "
        "plafond, la même attaque est enregistrée dix fois (voir "
        "deduplication.py). Mettre 0 pour désactiver.",
    )
    parser.add_argument(
        "--methodology-log",
        default=None,
        help="Chemin JSONL des sorties brutes de Layer 2, un enregistrement par chunk "
        "(Step 1 : à inspecter à la main avant de faire confiance à la table). "
        "Par défaut : results/methodology_<nom du pdf>.jsonl. Ignoré si "
        "plusieurs PDF sont traités (le défaut, un fichier par PDF, s'applique).",
    )
    args = parser.parse_args()

    pdfs = expand_pdf_paths(args.pdf)
    if not pdfs:
        raise SystemExit(f"[✗] Aucun PDF trouvé dans : {' '.join(args.pdf)}")
    if args.skip_existing:
        done = {r.get("source_paper") for r in load_table(args.table)}
        skipped = [p for p in pdfs if os.path.basename(p) in done]
        pdfs = [p for p in pdfs if os.path.basename(p) not in done]
        for p in skipped:
            print(f"[=] déjà dans {args.table}, sauté : {os.path.basename(p)}")
        if not pdfs:
            print_corpus_summary(args.table)
            return
    if len(pdfs) > 1:
        args.methodology_log = None

    taxonomy_label = attack_taxonomy.taxonomy_label(args.domain)
    print(f"Domaine : {args.domain} (référentiel {taxonomy_label}) — {len(pdfs)} paper(s) à traiter")
    gliner = GLiNERExtractor(labels=topic_config(args.domain)["labels"])
    print(f"Chargement du référentiel {taxonomy_label}...")
    techniques = attack_taxonomy.load_techniques(args.domain)
    mistral = MistralExtractor(backend=args.backend)
    methodology = MethodologyExtractor(
        mistral=mistral, techniques=techniques, domain=args.domain
    )

    failed = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"\n{'=' * 70}\nPaper {i}/{len(pdfs)} : {pdf}\n{'=' * 70}")
        try:
            process_pdf(pdf, args, gliner, methodology)
        except Exception as e:  # un PDF illisible ne doit pas arrêter tout le lot
            if len(pdfs) == 1:
                raise
            print(f"[✗] échec sur {pdf} : {e!r} — paper suivant")
            failed.append(pdf)

    print_corpus_summary(args.table)
    if failed:
        print(f"\n[✗] {len(failed)} paper(s) en échec, à relancer : " + " ".join(failed))


def expand_pdf_paths(paths: list[str]) -> list[str]:
    """Fichiers tels quels, dossiers remplacés par leurs .pdf (ordre alphabétique), sans doublon."""
    out = []
    for p in paths:
        found = sorted(glob.glob(os.path.join(p, "*.pdf"))) if os.path.isdir(p) else [p]
        out.extend(f for f in found if f not in out)
    return out


def print_corpus_summary(table_path: str) -> None:
    """Résumé de la table : cas par paper et par technique, mitigations non nulles."""
    table = load_table(table_path)
    if not table:
        return
    by_paper = Counter(r.get("source_paper") for r in table)
    by_cat = Counter(r.get("category") or "non validée" for r in table)
    with_mitigation = sum(1 for r in table if r.get("mitigation_summary"))
    print(f"\n{'=' * 70}\nTable {table_path} : {len(table)} cas, {len(by_paper)} paper(s), "
          f"{with_mitigation} avec mitigation, {len(by_cat)} technique(s)")
    for cat, n in by_cat.most_common():
        print(f"    {n:4}  {cat}")
    print("  par paper :")
    for paper, n in sorted(by_paper.items()):
        print(f"    {n:4}  {paper}")


def process_pdf(pdf: str, args, gliner: GLiNERExtractor, methodology: MethodologyExtractor) -> None:
    """Steps 1-5 pour UN paper, modèles déjà chargés."""
    print(f"[1/4] Lecture du PDF : {pdf}")
    text = extract_text_from_pdf(pdf)
    chunks = chunk_text(text)
    chunk_texts = [c for _, c in chunks]
    print(f"      -> {len(text)} caractères, {len(chunks)} chunk(s)")

    print(f"\n[2/4] Layer 1 : extraction d'entités (GLiNER, taxonomie {args.domain})")
    layer1_entities_per_chunk = [gliner.extract(chunk)["entities"] for _, chunk in chunks]
    total_entities = sum(len(e) for e in layer1_entities_per_chunk)
    print(f"      -> {total_entities} entité(s) au total sur {len(chunks)} chunk(s)")

    print("\n[3/4] Layer 2 : résumé attaque/mitigation (Steps 1-3)")

    source_paper = os.path.basename(pdf)
    methodology_log = args.methodology_log or os.path.join(
        "results", f"methodology_{os.path.splitext(source_paper)[0]}.jsonl"
    )
    # Un fichier par PDF -> repartir propre à chaque run plutôt que d'empiler
    # les résultats de runs précédents (le LLM n'étant pas déterministe, une
    # ré-exécution ne produit pas des doublons exacts mais des variantes
    # légèrement différentes, impossibles à filtrer après coup de façon
    # fiable).
    clear_jsonl(methodology_log)
    methodology_records = methodology.extract_from_chunks(
        chunk_texts,
        layer1_entities_per_chunk,
        source_paper=source_paper,
        jsonl_path=methodology_log,
    )
    n_attacks = sum(1 for r in methodology_records if r["attack_present"])
    print(f"      -> {n_attacks} chunk(s) avec attaque confirmée sur {len(chunks)}")
    print(f"      -> résultats bruts sauvegardés dans {methodology_log} (à inspecter à la main)")

    print("\n[4/4] Steps 4-5 : score de généralisabilité + ajout à la table de connaissance")
    attack_vectors_path, mitigation_vectors_path = vector_paths_for(args.table)
    added = build_table_from_methodology_records(
        methodology_records,
        layer1_entities_per_chunk,
        source_paper=source_paper,
        table_path=args.table,
        attack_vectors_path=attack_vectors_path,
        mitigation_vectors_path=mitigation_vectors_path,
        domain=args.domain,
        # 0 -> pas de plafond : on passe un nombre plus grand que le nombre de
        # chunks plutôt qu'une valeur sentinelle à tester partout en aval.
        max_per_category=args.max_per_category or len(chunks) + 1,
    )
    n_concrete = sum(1 for r in added if r["specificity"] == "concrete")
    n_generic = len(added) - n_concrete
    print(
        f"      -> {len(added)} enregistrement(s) ajouté(s) à {args.table} "
        f"({n_concrete} concret(s), {n_generic} générique(s) — voir "
        f"specificity.py : un cas générique reformule le sujet du papier "
        f"sans identifiant précis, ex: nom de paquet, CVE, date)"
    )

    for record in added:
        category = record["category"] or "catégorie non validée"
        tag = "concret" if record["specificity"] == "concrete" else "générique"
        print(f"\n  [{category}][{tag}] {record['attack_summary']}")
        if record["mitigation_summary"]:
            mitigation_type = record["mitigation_type"] or "type non validé"
            print(
                f"    mitigation [{mitigation_type}] : {record['mitigation_summary']} "
                f"(généralisabilité={record['generalizability_score']})"
            )
        else:
            print("    mitigation : aucune décrite dans le texte (null honnête)")


if __name__ == "__main__":
    main()
