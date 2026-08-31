"""
query_knowledge.py
--------------------
Point d'entrée en ligne de commande pour le retrieval Step 6 (Tier 1, et
Tier 2 si config.TIER2_ENABLED) sur la table de connaissance construite par
build_knowledge.py. Ne fait PAS la boucle Propose -> Verify -> Revise
(Step 7), volontairement non implémentée dans cette passe.

Usage :
    python query_knowledge.py --attack-summary "Backdoor introduite dans une
        bibliothèque de compression via un mainteneur compromis" --category T1195
"""

import argparse
import json

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
        "--category", default=None, help="ID MITRE ATT&CK de l'attaque, si connu (ex: T1195)."
    )
    parser.add_argument("--cve", default=None)
    parser.add_argument("--package", default=None)
    args = parser.parse_args()

    result = retrieve(
        query_attack_summary=args.attack_summary,
        query_category=args.category,
        cve=args.cve,
        package=args.package,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
