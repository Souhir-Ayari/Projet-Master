"""
query_knowledge.py
--------------------
Point d'entrée en ligne de commande pour le retrieval Step 6 (Tier 1, et
Tier 2 si config.TIER2_ENABLED) sur la table de connaissance construite par
build_knowledge.py. Ne fait PAS la boucle Propose -> Verify -> Revise
(Step 7), volontairement non implémentée dans cette passe.

Usage :
    python query_knowledge.py --attack-summary "Une page web récupérée par
        l'agent contient des instructions cachées qui lui font divulguer le
        contenu de sa fenêtre de contexte" --category AML.T0051.001

La catégorie attendue dépend du domaine du corpus interrogé : AML.Txxxx
(MITRE ATLAS) pour les papers "llm", Txxxx (MITRE ATT&CK) pour les papers
"supply_chain". Elle sert de bonus de similarité, jamais de filtre — une
catégorie du mauvais référentiel ne fait donc que ne matcher aucun
enregistrement, sans casser la recherche.
"""

import argparse
import json

from config import KNOWLEDGE_TABLE_PATH
from knowledge_table import load_table, vector_paths_for
from retrieval import retrieve


def main():
    parser = argparse.ArgumentParser(
        description="Cherche les cas les plus proches dans la table de connaissance (Step 6)."
    )
    parser.add_argument(
        "--attack-summary",
        required=True,
        help="Description de la nouvelle attaque à rapprocher.",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="ID MITRE de l'attaque, si connu : AML.Txxxx (ATLAS, corpus LLM, "
        "ex: AML.T0051.001) ou Txxxx (ATT&CK, corpus supply chain, ex: T1195).",
    )
    parser.add_argument("--cve", default=None)
    parser.add_argument("--package", default=None)
    parser.add_argument(
        "--table",
        default=KNOWLEDGE_TABLE_PATH,
        help="Table de connaissance à interroger (par défaut : "
        "config.KNOWLEDGE_TABLE_PATH). Le store vectoriel associé est déduit "
        "du nom de la table, comme à la construction — sans ça, interroger un "
        "corpus séparé lisait ses textes mais les vecteurs de l'autre.",
    )
    args = parser.parse_args()

    attack_vectors_path, _ = vector_paths_for(args.table)
    result = retrieve(
        query_attack_summary=args.attack_summary,
        query_category=args.category,
        cve=args.cve,
        package=args.package,
        table=load_table(args.table),
        attack_vectors_path=attack_vectors_path,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
