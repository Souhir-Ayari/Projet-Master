"""
run_remediation.py
--------------------
Orchestrateur CLI de la boucle Propose -> Verify -> Revise (Step 7, voir
remediation.py) sur les requêtes du Bloc 1, dans les trois modes de la
Table IV (RQ3) :

    no_retrieval    single-shot, sans cas récupérés
    retrieval       Propose sur les cas récupérés, sans boucle
    retrieval_loop  Propose + Verify + Revise (N=1)

Par défaut, les requêtes sont les trois requêtes de calibration du retrieval
(pertinente / moyennement pertinente / hors domaine) : ce sont les « mêmes
3-4 queries du bloc 1 » demandées par le plan. La requête hors domaine sert
de contrôle : le comportement attendu est une ABSTENTION (plan vide), pas
une liste de défenses.

La table de connaissance est FIGÉE : son empreinte SHA-256 est enregistrée
dans chaque résultat. Si la table change entre deux runs, l'empreinte le
montre — les chiffres de la Table IV ne sont comparables qu'à empreinte égale.

Usage :
    python run_remediation.py --table results/knowledge_table_llm.jsonl
    python run_remediation.py --table results/knowledge_table_llm.jsonl --output-dir results/rq3
    python run_remediation.py --table ... --modes retrieval_loop --queries mes_requetes.json

Format de --queries : liste JSON de {"name": ..., "attack_summary": ..., "category": ... (optionnel)}.
"""

import argparse
import hashlib
import json
import os
import time

from config import KNOWLEDGE_TABLE_PATH, OLLAMA_MODEL_NAME, TIER2_ENABLED
from knowledge_table import load_table, vector_paths_for
from remediation import MIN_LEXICAL_SUPPORT, MODES, Remediator
from retrieval import VectorStoreError, check_vector_store, retrieve

DEFAULT_QUERIES = [
    {
        "name": "relevant",
        "attack_summary": (
            "An attacker injects malicious instructions into an LLM-integrated "
            "application to manipulate its behavior"
        ),
        "category": "AML.T0051.001",
    },
    {
        "name": "medium_relevance",
        "attack_summary": (
            "A malicious actor exploits weaknesses in an AI-powered software system "
            "by influencing information processed by the model, causing the "
            "application to produce attacker-controlled outcomes"
        ),
        "category": None,
    },
    {
        "name": "out_of_domain",
        "attack_summary": (
            "The Eiffel Tower was constructed in Paris for the 1889 World's Fair "
            "and is one of the most famous landmarks in France"
        ),
        "category": None,
    },
]


def file_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _fmt(value) -> str:
    return "—" if value is None else f"{value:.2f}"


def main():
    parser = argparse.ArgumentParser(
        description="Boucle Propose-Verify-Revise (Step 7) sur les requêtes du Bloc 1 -> Table IV."
    )
    parser.add_argument("--table", default=KNOWLEDGE_TABLE_PATH)
    parser.add_argument("--output-dir", default="results/rq3")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--queries", default=None, help="Fichier JSON de requêtes (sinon les 3 requêtes du Bloc 1).")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    table = load_table(args.table)
    if not table:
        raise SystemExit(f"[✗] Table vide ou absente : {args.table}")
    attack_vectors_path, _ = vector_paths_for(args.table)
    # Sans cas récupérés, les trois modes tourneraient à vide et Verify
    # rejetterait tout : mieux vaut s'arrêter avec la vraie cause.
    try:
        check_vector_store(table, attack_vectors_path)
    except VectorStoreError as e:
        raise SystemExit(f"[✗] {e}")
    table_hash = file_sha256(args.table)

    if args.queries:
        with open(args.queries, encoding="utf-8") as f:
            queries = json.load(f)
    else:
        queries = DEFAULT_QUERIES

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Table : {args.table} ({len(table)} enregistrements, sha256 {table_hash[:12]}…)")
    print(f"Modèle : {OLLAMA_MODEL_NAME} — modes : {', '.join(args.modes)}\n")

    remediator = Remediator()
    summary_rows = []
    for query in queries:
        print(f"=== {query['name']}")
        retrieval_result = retrieve(
            query_attack_summary=query["attack_summary"],
            query_category=query.get("category"),
            table=table,
            attack_vectors_path=attack_vectors_path,
        )
        cases = retrieval_result["tier1_results"][: args.top_k]
        print(f"    {len(cases)} cas récupérés, best_score={retrieval_result['best_score']:.3f}"
              f" (tier2_would_trigger={retrieval_result['tier2_would_trigger']})")

        record = {
            "query": query,
            "table": args.table,
            "table_sha256": table_hash,
            "model": OLLAMA_MODEL_NAME,
            "tier2_enabled": TIER2_ENABLED,
            "min_lexical_support": MIN_LEXICAL_SUPPORT,
            "retrieval": {
                "best_score": retrieval_result["best_score"],
                "threshold": retrieval_result["threshold"],
                "tier2_would_trigger": retrieval_result["tier2_would_trigger"],
                "cases": [
                    {k: c.get(k) for k in (
                        "record_id", "source_paper", "category", "similarity_score",
                        "attack_summary", "mitigation_type", "mitigation_summary",
                    )}
                    for c in cases
                ],
            },
            "runs": {},
        }

        for mode in args.modes:
            start = time.time()
            run = remediator.run(
                query["attack_summary"], cases, mode,
                min_similarity=retrieval_result["threshold"],
            )
            run["seconds"] = round(time.time() - start, 1)
            record["runs"][mode] = run
            print(
                f"    [{mode:15}] {run['n_recommendations']} recommandation(s), "
                f"traçabilité={_fmt(run['traceability_rate'])}, "
                f"appels LLM={run['n_llm_calls']}"
                + (", révision déclenchée" if run["revision_triggered"] else "")
                + (", ABSTENTION : aucun cas au-dessus du seuil" if run["abstained_no_case"] else "")
                + (f", {run['n_parse_errors']} JSON invalide(s)" if run["n_parse_errors"] else "")
            )
            for rec in run["final_plan"]:
                mark = "✓" if rec["traceable"] else "✗"
                print(f"        {mark} [{rec.get('mitigation_type')}] {rec.get('action')} "
                      f"<- {rec.get('cited_cases')}")
            summary_rows.append({
                "query": query["name"],
                "mode": mode,
                "n_recommendations": run["n_recommendations"],
                "traceability_rate": run["traceability_rate"],
                "supported_rate": run["supported_rate"],
                "revision_triggered": run["revision_triggered"],
                "n_rejected_initial": run["n_rejected_initial"],
                "n_dropped": len(run.get("dropped") or []),
                "n_duplicates": len(run.get("duplicates") or []),
                "n_eligible_cases": run["n_eligible_cases"],
                "abstained_no_case": run["abstained_no_case"],
                "n_parse_errors": run["n_parse_errors"],
                "n_llm_calls": run["n_llm_calls"],
                "seconds": run["seconds"],
            })

        path = os.path.join(args.output_dir, f"remediation_{query['name']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        print(f"    -> {path}\n")

    summary = {
        "table": args.table,
        "table_sha256": table_hash,
        "model": OLLAMA_MODEL_NAME,
        "rows": summary_rows,
    }
    summary_path = os.path.join(args.output_dir, "table_iv_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("TABLE IV (brouillon) — traçabilité = part des recommandations finales "
          "traçables vers un cas récupéré ; — = plan vide (abstention)")
    print(f"{'requête':18} {'mode':16} {'cas':>3} {'#reco':>5} {'traçab.':>8} {'ancrée':>7} "
          f"{'rejets':>6} {'écartées':>8} {'doubl.':>6} {'JSON✗':>5} {'appels':>6}")
    for row in summary_rows:
        print(f"{row['query']:18} {row['mode']:16} {row['n_eligible_cases']:>3} "
              f"{row['n_recommendations']:>5} "
              f"{_fmt(row['traceability_rate']):>8} {_fmt(row['supported_rate']):>7} "
              f"{row['n_rejected_initial']:>6} {row['n_dropped']:>8} {row['n_duplicates']:>6} "
              f"{row['n_parse_errors']:>5} {row['n_llm_calls']:>6}")
    print("cas = cas récupérés au-dessus du seuil de similarité (seuls citables) ; "
          "JSON✗ = réponses invalides, récupérées recommandation par recommandation")
    print(f"\n[✓] Résumé : {summary_path}")


if __name__ == "__main__":
    main()
