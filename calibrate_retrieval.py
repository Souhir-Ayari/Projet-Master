"""
calibrate_retrieval.py
------------------------
Calibration du retrieval Tier 1 sur des requêtes étiquetées
(data/eval_queries.json), pour remplacer les valeurs choisies à la main de
α (bonus de catégorie) et θ (seuil de couverture) par des valeurs DÉRIVÉES
des données — demandé pour le §4.1 du papier.

Les embeddings des requêtes sont calculés UNE fois (Ollama), puis chaque
réglage est évalué sur les mêmes similarités via retrieval.score_cases.

1. α et filtre par catégorie : pour chaque réglage, Hit@1, Hit@3 et MRR sur
   les requêtes dont la catégorie est représentée dans la table (un cas
   remonté est pertinent si sa catégorie est dans "expected"). Le détail par
   requête montre quel réglage fait remonter quel cas — notamment le cas
   AML.T0020 sur la requête d'empoisonnement de données.

2. θ : dérivé du cosinus BRUT du meilleur cas (sans bonus, donc indépendant
   de α). Une requête "couverte" (catégorie présente dans la table) doit
   passer le seuil, une requête hors corpus non. Pour chaque θ candidat, on
   mesure l'exactitude équilibrée de cette décision ; le script rapporte
   l'intervalle des θ optimaux et la valeur actuelle.

Limite à garder en tête (et à écrire) : calibrer et évaluer sur les mêmes
18 requêtes surestime la qualité du réglage. Le script rapporte donc aussi
l'exactitude de θ en leave-one-out (θ choisi sans la requête évaluée).

Usage :
    python calibrate_retrieval.py --table results/knowledge_table_llm.jsonl
"""

import argparse
import json
import os
import time

from config import RETRIEVAL_CATEGORY_BONUS, RETRIEVAL_SIMILARITY_THRESHOLD
from jsonl_utils import save_run_json
from knowledge_table import embed_text, load_table, vector_paths_for
from retrieval import VectorStoreError, check_vector_store, score_cases
from vector_store import cosine_similarities, load_vectors

ALPHAS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
THETAS = [round(0.40 + 0.01 * i, 2) for i in range(51)]  # 0.40 .. 0.90


def rank_metrics(ranked: list[dict], expected: set) -> tuple[int, int, float]:
    """(hit@1, hit@3, reciprocal rank) d'une liste classée de cas."""
    rr = 0.0
    for rank, case in enumerate(ranked, 1):
        if case.get("category") in expected:
            rr = 1.0 / rank
            break
    hit1 = int(bool(ranked) and ranked[0].get("category") in expected)
    hit3 = int(any(c.get("category") in expected for c in ranked[:3]))
    return hit1, hit3, rr


def balanced_accuracy(theta: float, items: list[tuple[float, bool]]) -> float:
    """items = (meilleur cosinus brut, couverte?) ; couverte doit passer θ, hors corpus non."""
    pos = [c for c, covered in items if covered]
    neg = [c for c, covered in items if not covered]
    tpr = sum(c >= theta for c in pos) / len(pos) if pos else 0.0
    tnr = sum(c < theta for c in neg) / len(neg) if neg else 0.0
    return (tpr + tnr) / 2


def best_thetas(items: list[tuple[float, bool]]) -> tuple[float, list[float]]:
    scores = {t: balanced_accuracy(t, items) for t in THETAS}
    top = max(scores.values())
    return top, [t for t, s in scores.items() if s == top]


def main():
    parser = argparse.ArgumentParser(description="Calibre α et θ du retrieval sur des requêtes étiquetées.")
    parser.add_argument("--table", required=True)
    parser.add_argument("--queries", default="data/eval_queries.json")
    parser.add_argument("--output-dir", default="results/calibration")
    args = parser.parse_args()

    table = load_table(args.table)
    if not table:
        raise SystemExit(f"[✗] Table vide ou absente : {args.table}")
    attack_vectors_path, _ = vector_paths_for(args.table)
    try:
        check_vector_store(table, attack_vectors_path)
    except VectorStoreError as e:
        raise SystemExit(f"[✗] {e}")
    record_by_id = {r["record_id"]: r for r in table}
    ids, matrix = load_vectors(attack_vectors_path)
    table_categories = {r.get("category") for r in table if r.get("category")}

    with open(args.queries, encoding="utf-8") as f:
        queries = json.load(f)["queries"]

    print(f"Table : {args.table} ({len(table)} cas) — {len(queries)} requêtes, embeddings via Ollama...")
    for q in queries:
        q["similarities"] = cosine_similarities(embed_text(q["attack_summary"]), matrix)
        # "Couverte" se lit dans la table réelle, pas dans l'étiquette écrite à la main.
        q["covered"] = bool(set(q["expected"]) & table_categories)
        if q["covered"] != q["in_corpus"]:
            print(f"[⚠] {q['name']} : in_corpus={q['in_corpus']} mais couverte={q['covered']} dans cette table")

    covered = [q for q in queries if q["covered"]]

    # --- 1. α et filtre --------------------------------------------------
    configs = [("bonus", a, False) for a in ALPHAS] + [("filtre", RETRIEVAL_CATEGORY_BONUS, True)]
    config_rows, per_query = [], {q["name"]: {} for q in covered}
    print(f"\n1) α / filtre — {len(covered)} requêtes couvertes")
    print(f"{'réglage':16} {'Hit@1':>6} {'Hit@3':>6} {'MRR':>6}")
    for kind, alpha, filt in configs:
        label = "filtre catégorie" if filt else f"α = {alpha:.2f}"
        h1 = h3 = rr = 0.0
        for q in covered:
            ranked = score_cases(q["similarities"], ids, record_by_id, q["category"],
                                 category_bonus=alpha, category_filter=filt, top_k=len(table))
            a, b, c = rank_metrics(ranked, set(q["expected"]))
            h1, h3, rr = h1 + a, h3 + b, rr + c
            per_query[q["name"]][label] = {
                "top3": [(c_["category"], c_["similarity_score"]) for c_ in ranked[:3]],
                "hit@3": b,
            }
        n = len(covered)
        row = {"config": label, "alpha": alpha, "filter": filt,
               "hit@1": round(h1 / n, 3), "hit@3": round(h3 / n, 3), "mrr": round(rr / n, 3)}
        config_rows.append(row)
        mark = "  <- actuel" if (not filt and alpha == RETRIEVAL_CATEGORY_BONUS) else ""
        print(f"{label:16} {row['hit@1']:>6.3f} {row['hit@3']:>6.3f} {row['mrr']:>6.3f}{mark}")

    print("\n   Requêtes dont le résultat change selon le réglage :")
    for name, by_cfg in per_query.items():
        if len({v["hit@3"] for v in by_cfg.values()}) > 1:
            print(f"   - {name} : " + ", ".join(f"{k}={'✓' if v['hit@3'] else '✗'}" for k, v in by_cfg.items()))

    # --- 2. θ ------------------------------------------------------------
    items = [(float(max(q["similarities"])), q["covered"]) for q in queries]
    top, thetas = best_thetas(items)
    loo_correct = 0
    for i, (cos, cov) in enumerate(items):
        _, th = best_thetas(items[:i] + items[i + 1:])
        t = th[len(th) // 2]
        loo_correct += int((cos >= t) == cov)
    print(f"\n2) θ — meilleur cosinus brut par requête (couverte doit passer θ, hors corpus non)")
    for q, (cos, cov) in sorted(zip(queries, items), key=lambda x: -x[1][0]):
        print(f"   {cos:.3f}  {'couverte  ' if cov else 'hors corpus'}  {q['name']}")
    print(f"   θ optimaux : {thetas[0]:.2f} – {thetas[-1]:.2f} (exactitude équilibrée {top:.3f})")
    for t in sorted({RETRIEVAL_SIMILARITY_THRESHOLD, 0.7}):
        print(f"   θ = {t:.2f} : exactitude équilibrée {balanced_accuracy(t, items):.3f}")
    print(f"   leave-one-out : {loo_correct}/{len(items)} requêtes bien classées")

    payload = {
        "run": {"script": "calibrate_retrieval.py", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "table": args.table, "n_cases": len(table), "queries": args.queries},
        "alpha_filter": config_rows,
        "per_query": per_query,
        "theta": {"best_balanced_accuracy": top, "best_range": [thetas[0], thetas[-1]],
                  "leave_one_out_correct": loo_correct, "n_queries": len(items),
                  "best_cosine_per_query": [{"name": q["name"], "best_cosine": round(c, 4), "covered": cov}
                                            for q, (c, cov) in zip(queries, items)]},
    }
    path = save_run_json(payload, args.output_dir, "calibration")
    print(f"\n[✓] {path}")


if __name__ == "__main__":
    main()
