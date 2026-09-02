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
"""

import argparse
import os

import attack_taxonomy
from config import DEFAULT_DOMAIN, KNOWLEDGE_TABLE_PATH, topic_config
from gliner_extractor import GLiNERExtractor
from jsonl_utils import clear_jsonl
from knowledge_table import build_table_from_methodology_records
from methodology_extractor import MethodologyExtractor
from mistral_extractor import MistralExtractor
from pdf_extractor import chunk_text, extract_text_from_pdf


def main():
    parser = argparse.ArgumentParser(
        description="Construit/complète la table de connaissance à partir d'UN paper (Steps 1-5)."
    )
    parser.add_argument("--pdf", required=True, help="Chemin vers le PDF d'entrée")
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
        help="Chemin de la table de connaissance JSONL (par défaut : config.KNOWLEDGE_TABLE_PATH)",
    )
    parser.add_argument(
        "--methodology-log",
        default=None,
        help="Chemin JSONL des sorties brutes de Layer 2, un enregistrement par chunk "
        "(Step 1 : à inspecter à la main avant de faire confiance à la table). "
        "Par défaut : results/methodology_<nom du pdf>.jsonl",
    )
    args = parser.parse_args()

    taxonomy_label = attack_taxonomy.taxonomy_label(args.domain)
    print(f"[1/4] Lecture du PDF : {args.pdf}")
    print(f"      domaine : {args.domain} (référentiel {taxonomy_label})")
    text = extract_text_from_pdf(args.pdf)
    chunks = chunk_text(text)
    chunk_texts = [c for _, c in chunks]
    print(f"      -> {len(text)} caractères, {len(chunks)} chunk(s)")

    print(f"\n[2/4] Layer 1 : extraction d'entités (GLiNER, taxonomie {args.domain})")
    gliner = GLiNERExtractor(labels=topic_config(args.domain)["labels"])
    layer1_entities_per_chunk = [gliner.extract(chunk)["entities"] for _, chunk in chunks]
    total_entities = sum(len(e) for e in layer1_entities_per_chunk)
    print(f"      -> {total_entities} entité(s) au total sur {len(chunks)} chunk(s)")

    print("\n[3/4] Layer 2 : résumé attaque/mitigation (Steps 1-3)")
    print(f"      Chargement du référentiel {taxonomy_label}...")
    techniques = attack_taxonomy.load_techniques(args.domain)
    mistral = MistralExtractor(backend=args.backend)
    methodology = MethodologyExtractor(
        mistral=mistral, techniques=techniques, domain=args.domain
    )

    source_paper = os.path.basename(args.pdf)
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
    added = build_table_from_methodology_records(
        methodology_records,
        layer1_entities_per_chunk,
        source_paper=source_paper,
        table_path=args.table,
        domain=args.domain,
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
