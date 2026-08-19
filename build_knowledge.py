"""
build_knowledge.py
--------------------
Orchestrateur OFFLINE du pipeline méthodologie/mitigation (Steps 1-5) :

    PDF -> texte -> chunks
       -> Layer 1 : extraction d'entités (existant, INCHANGÉ - main.py)
       -> Layer 2 : résumé attaque/mitigation ancré sur le texte + les
          entités Layer 1 (Step 1), catégorie MITRE ATT&CK validée (Step 2),
          mitigation conservée seulement si attaque + catégorie confirmées
          (Step 3)
       -> score de généralisabilité (Step 4)
       -> knowledge_table.jsonl (Step 5), qui grossit avec chaque nouveau
          paper traité

À lancer UNE FOIS par paper du corpus (viser 15-30+ papers avant que le
retrieval, Step 6 - voir retrieval.py/query_knowledge.py - soit significatif).
Réutilise GLiNER/Mistral, ne les duplique pas.

Usage :
    python build_knowledge.py --pdf backdoor.pdf
    python build_knowledge.py --pdf backdoor.pdf --table results/knowledge_table.jsonl
"""

import argparse
import os

import attack_taxonomy
from config import KNOWLEDGE_TABLE_PATH, SUPPLY_CHAIN_ENTITY_LABELS
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

    print(f"[1/4] Lecture du PDF : {args.pdf}")
    text = extract_text_from_pdf(args.pdf)
    chunks = chunk_text(text)
    chunk_texts = [c for _, c in chunks]
    print(f"      -> {len(text)} caractères, {len(chunks)} chunk(s)")

    print(
        "\n[2/4] Layer 1 : extraction d'entités (GLiNER, taxonomie chaîne d'approvisionnement)"
    )
    gliner = GLiNERExtractor(labels=SUPPLY_CHAIN_ENTITY_LABELS)
    layer1_entities_per_chunk = [gliner.extract(chunk)["entities"] for _, chunk in chunks]
    total_entities = sum(len(e) for e in layer1_entities_per_chunk)
    print(f"      -> {total_entities} entité(s) au total sur {len(chunks)} chunk(s)")

    print("\n[3/4] Layer 2 : résumé attaque/mitigation (Steps 1-3)")
    print("      Chargement du référentiel MITRE ATT&CK...")
    techniques = attack_taxonomy.load_techniques()
    mistral = MistralExtractor(backend=args.backend)
    methodology = MethodologyExtractor(mistral=mistral, techniques=techniques)

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
    )
    print(f"      -> {len(added)} enregistrement(s) ajouté(s) à {args.table}")

    for record in added:
        category = record["category"] or "catégorie non validée"
        print(f"\n  [{category}] {record['attack_summary']}")
        if record["mitigation_summary"]:
            print(
                f"    mitigation : {record['mitigation_summary']} "
                f"(généralisabilité={record['generalizability_score']})"
            )
        else:
            print("    mitigation : aucune décrite dans le texte (null honnête)")


if __name__ == "__main__":
    main()
