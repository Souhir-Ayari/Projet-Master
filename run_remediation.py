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

Format de --queries : liste JSON de {"name": ..., "attack_summary": ..., "category": ... (optionnel)},
ou objet {"queries": [...]} comme data/eval_queries.json.

Vérificateurs (--verifiers, plusieurs possibles pour l'ablation) :
    lexical  ancrage lexical historique (récompense la copie) — ablation
    rule     adaptation causale ; la règle seule décide (maillon déduit)
    labels   adaptation causale ; le modèle étiquette le maillon, la règle décide (principal)
    llm      adaptation causale ; le modèle juge tout (référence auto-critique)
Table IV sur les 18 requêtes, table brute + borne supérieure :
    python run_remediation.py --table results/knowledge_table_llm_raw.jsonl --queries data/eval_queries.json \
        --verifiers labels lexical rule llm --unanchored --output-dir results/rq3_raw
    python run_remediation.py --table results/knowledge_table_llm_curated.jsonl --queries data/eval_queries.json \
        --verifiers labels --unanchored --output-dir results/rq3_curated
"""

import argparse
import hashlib
import json
import os
import time

from config import KNOWLEDGE_TABLE_PATH, OLLAMA_MODEL_NAME, TIER2_ENABLED
from knowledge_table import load_table, vector_paths_for
from causal import LINK_MIN, SEMANTIC_MIN
from remediation import MIN_LEXICAL_SUPPORT, MODES, VERIFIERS, Remediator
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


def summary_row(query: dict, mode: str, verifier: str, run: dict) -> dict:
    return {
        "query": query["name"],
        "in_corpus": query.get("in_corpus"),
        "mode": mode,
        "verifier": verifier,
        "max_iterations": run.get("max_iterations", 1),
        "iterations": run.get("iterations"),
        "n_recommendations": run["n_recommendations"],
        "traceability_rate": run["traceability_rate"],
        "supported_rate": run["supported_rate"],
        "adaptation_rate": run.get("adaptation_rate"),
        "causal_adequacy_rate": run.get("causal_adequacy_rate"),
        "citation_inferred_rate": run.get("citation_inferred_rate"),
        "unanchored": run.get("unanchored", False),
        "revision_triggered": run["revision_triggered"],
        "n_rejected_initial": run["n_rejected_initial"],
        "n_dropped": len(run.get("dropped") or []),
        "n_duplicates": len(run.get("duplicates") or []),
        "n_eligible_cases": run["n_eligible_cases"],
        "abstained_no_case": run["abstained_no_case"],
        "n_parse_errors": run["n_parse_errors"],
        "n_llm_calls": run["n_llm_calls"],
        "seconds": run["seconds"],
    }


def run_key(mode: str, verifier: str, verifiers: list[str], n: int = 1, iterations: list[int] = (1,)) -> str:
    key = mode if verifier == "lexical" and len(verifiers) == 1 else f"{mode}|{verifier}"
    # Ablation sur N : une clé par budget de révisions (seulement si plusieurs N)
    return f"{key}|N{n}" if len(iterations) > 1 and mode == "retrieval_loop" else key


def configurations(modes: list[str], verifiers: list[str], iterations: list[int]):
    """(mode, vérificateur, N) ; N ne varie que pour la boucle."""
    for v in verifiers:
        for m in modes:
            for n in (iterations if m == "retrieval_loop" else [1]):
                yield m, v, n


def main():
    parser = argparse.ArgumentParser(
        description="Boucle Propose-Verify-Revise (Step 7) sur les requêtes du Bloc 1 -> Table IV."
    )
    parser.add_argument("--table", default=KNOWLEDGE_TABLE_PATH)
    parser.add_argument("--output-dir", default="results/rq3")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--queries", default=None, help="Fichier JSON de requêtes (sinon les 3 requêtes du Bloc 1).")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--verifiers", nargs="+", choices=VERIFIERS, default=["labels"])
    parser.add_argument("--calibration", default=None,
                        help="JSON produit par calibrate_causal.py : seuils sémantique et maillon calibrés "
                             "sur des données de développement (sinon : seuils a priori de causal.py)")
    parser.add_argument("--semantic-min", type=float, default=None, help="force le seuil sémantique")
    parser.add_argument("--link-min", type=float, default=None, help="force le seuil maillon")
    parser.add_argument("--resume", action="store_true",
                        help="reprendre un run interrompu : une requête dont le fichier de sortie existe déjà "
                             "(même table, mêmes seuils, mêmes modes et vérificateurs) n'est pas relancée")
    parser.add_argument("--iterations", nargs="+", type=int, default=[1],
                        help="budget(s) de révisions N de la boucle ; plusieurs valeurs = ablation (ex. 0 1 2 3)")
    parser.add_argument("--unanchored", action="store_true",
                        help="branche non ancrée : proposer quand même (marqué) quand aucun cas ne passe θ")
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
        if isinstance(queries, dict):
            queries = queries["queries"]
    else:
        queries = DEFAULT_QUERIES

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Table : {args.table} ({len(table)} enregistrements, sha256 {table_hash[:12]}…)")
    print(f"Modèle : {OLLAMA_MODEL_NAME} — modes : {', '.join(args.modes)}\n")

    semantic_min, link_min, threshold_source = SEMANTIC_MIN, LINK_MIN, "a priori (causal.py)"
    if args.calibration:
        with open(args.calibration, encoding="utf-8") as f:
            calib = json.load(f)
        semantic_min, link_min = calib["semantic_min"], calib["link_min"]
        threshold_source = f"calibrés ({args.calibration})"
    if args.semantic_min is not None:
        semantic_min, threshold_source = args.semantic_min, "forcés en ligne de commande"
    if args.link_min is not None:
        link_min, threshold_source = args.link_min, "forcés en ligne de commande"
    print(f"Seuils du vérificateur causal : sémantique={semantic_min}, maillon={link_min} — {threshold_source}\n")

    remediator = Remediator(semantic_min=semantic_min, link_min=link_min)
    summary_rows = []
    for qi, query in enumerate(queries, 1):
        path = os.path.join(args.output_dir, f"remediation_{query['name']}.json")
        if args.resume and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                previous = json.load(f)
            keys = [(m, v, run_key(m, v, args.verifiers, n, args.iterations))
                    for m, v, n in configurations(args.modes, args.verifiers, args.iterations)]
            if (previous.get("table_sha256") == table_hash
                    and previous.get("semantic_min") == semantic_min and previous.get("link_min") == link_min
                    and previous.get("unanchored_branch") == args.unanchored
                    and all(k in previous["runs"] for _, _, k in keys)):
                print(f"=== [{qi}/{len(queries)}] {query['name']} : déjà fait ({path}), repris")
                summary_rows += [summary_row(query, m, v, previous["runs"][k]) for m, v, k in keys]
                continue
            print(f"[⚠] {path} ne correspond pas à cette configuration : requête relancée")
        print(f"=== [{qi}/{len(queries)}] {query['name']}  ({time.strftime('%H:%M:%S')})")
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
            "semantic_min": semantic_min,
            "link_min": link_min,
            "threshold_source": threshold_source,
            "unanchored_branch": args.unanchored,
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

        for mode, verifier, n_iter in configurations(args.modes, args.verifiers, args.iterations):
            start = time.time()
            run = remediator.run(
                query["attack_summary"], cases, mode,
                min_similarity=retrieval_result["threshold"],
                verifier=verifier, unanchored_branch=args.unanchored, max_iterations=n_iter,
            )
            run["seconds"] = round(time.time() - start, 1)
            key = run_key(mode, verifier, args.verifiers, n_iter, args.iterations)
            record["runs"][key] = run
            label = f"{verifier}" + (f" N={n_iter}" if len(args.iterations) > 1 and mode == "retrieval_loop" else "")
            print(
                f"    [{mode:15} {label:10}] {run['n_recommendations']} recommandation(s), "
                f"traçabilité={_fmt(run['traceability_rate'])}, "
                f"adaptation={_fmt(run.get('adaptation_rate'))}, "
                f"adéquation causale={_fmt(run.get('causal_adequacy_rate'))}, "
                f"citations inférées={_fmt(run.get('citation_inferred_rate'))}, "
                f"appels LLM={run['n_llm_calls']}"
                + (", révision déclenchée" if run["revision_triggered"] else "")
                + (", NON ANCRÉ" if run.get("unanchored") else
                   ", ABSTENTION : aucun cas au-dessus du seuil" if run["abstained_no_case"] else "")
                + (f", {run['n_parse_errors']} JSON invalide(s)" if run["n_parse_errors"] else "")
            )
            for rec in run["final_plan"]:
                mark = "~" if rec.get("unanchored") else "✓" if rec["traceable"] else "✗"
                print(f"        {mark} [{rec.get('broken_link', '-')}] {rec.get('action')} "
                      f"<- {rec.get('cited_cases')}" + (" (citation inférée)" if rec.get("citation_inferred") else ""))
            summary_rows.append(summary_row(query, mode, verifier, run))

        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        print(f"    -> {path}\n")

    summary = {
        "semantic_min": semantic_min,
        "link_min": link_min,
        "threshold_source": threshold_source,
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
    print(f"{'requête':26} {'mode':15} {'vérif.':7} {'cas':>3} {'#reco':>5} {'traçab.':>8} "
          f"{'adapt.':>7} {'causal':>7} {'rejets':>6} {'écartées':>8} {'JSON✗':>5} {'appels':>6}")
    for row in summary_rows:
        print(f"{row['query']:26} {row['mode']:15} {row['verifier']:7} {row['n_eligible_cases']:>3} "
              f"{row['n_recommendations']:>5}{'~' if row['unanchored'] else ' '}"
              f"{_fmt(row['traceability_rate']):>7} {_fmt(row['adaptation_rate']):>7} "
              f"{_fmt(row['causal_adequacy_rate']):>7} "
              f"{row['n_rejected_initial']:>6} {row['n_dropped']:>8} "
              f"{row['n_parse_errors']:>5} {row['n_llm_calls']:>6}")

    # Agrégats par (mode, vérificateur) sur les requêtes couvertes : ce sont
    # les lignes de la Table IV. Les requêtes hors corpus sont comptées à part.
    print("\nAgrégats (requêtes couvertes ; recommandations poolées) :")
    groups = {}
    for row in summary_rows:
        groups.setdefault((row["mode"], row["verifier"], row["max_iterations"]), []).append(row)
    aggregates = []
    for (mode, verifier, n_iter), rows in groups.items():
        cov = [r for r in rows if r["in_corpus"] is not False]
        ood = [r for r in rows if r["in_corpus"] is False]
        n = sum(r["n_recommendations"] for r in cov)
        def pooled(key):
            vals = [(r[key], r["n_recommendations"]) for r in cov if r[key] is not None and r["n_recommendations"]]
            tot = sum(w for _, w in vals)
            return round(sum(v * w for v, w in vals) / tot, 3) if tot else None
        agg = {"mode": mode, "verifier": verifier, "max_iterations": n_iter, "n_recommendations": n,
               "queries_served": sum(r["n_recommendations"] > 0 for r in cov), "n_in_corpus": len(cov),
               "ood_recommendations": sum(r["n_recommendations"] for r in ood if not r["unanchored"]),
               "traceability": pooled("traceability_rate"), "adaptation": pooled("adaptation_rate"),
               "causal_adequacy": pooled("causal_adequacy_rate"),
               "citation_inferred": pooled("citation_inferred_rate"),
               "ood_abstained": sum(r["abstained_no_case"] and not r["unanchored"] for r in ood),
               "ood_unanchored": sum(r["unanchored"] for r in ood), "n_ood": len(ood),
               "llm_calls": sum(r["n_llm_calls"] for r in rows)}
        aggregates.append(agg)
        print(f"  {mode:15} {verifier:10} N={n_iter} reco={n:3} servies={agg['queries_served']}/{len(cov)} "
              f"traçab.={_fmt(agg['traceability'])} "
              f"adapt.={_fmt(agg['adaptation'])} causal={_fmt(agg['causal_adequacy'])} "
              f"cit. inférées={_fmt(agg['citation_inferred'])} "
              f"hors corpus : {agg['ood_recommendations']} reco ancrée(s), {agg['ood_abstained']} abstention(s), "
              f"{agg['ood_unanchored']} non ancré(s) "
              f"sur {len(ood)} ; appels={agg['llm_calls']}")
    summary["aggregates"] = aggregates
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("cas = cas récupérés au-dessus du seuil de similarité (seuls citables) ; "
          "JSON✗ = réponses invalides, récupérées recommandation par recommandation")
    print(f"Appels Mistral évités grâce au cache (prompts identiques entre vérificateurs) : "
          f"{remediator.n_cache_hits}")
    print(f"\n[✓] Résumé : {summary_path}")


if __name__ == "__main__":
    main()
