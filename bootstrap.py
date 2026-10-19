"""
bootstrap.py
-------------
Intervalles de confiance bootstrap (percentiles 2,5 / 97,5) des métriques
des Tables 2 et 3, en rééchantillonnant les REQUÊTES avec remise (10 000
tirages par défaut, graine fixe). Aucun appel à Mistral : le script relit les
sorties déjà produites.

  table2  sortie de calibrate_retrieval.py (per_query : hit@1, hit@3, rr par
          réglage) -> Hit@1, Hit@3, MRR avec IC, par réglage.
  table3  un ou plusieurs table_iv_summary.json (run_remediation.py) ->
          pour chaque configuration (mode, vérificateur, N) : groundedness,
          hallucination (vérificateur lexical), adaptation, adéquation
          causale (taux poolés sur les recommandations des requêtes
          couvertes, comme dans la Table 3), part des requêtes servies et
          recommandations ancrées par sonde hors corpus, avec IC.

Usage :
    python bootstrap.py table2 --calibration results/calibration/calibration_XXXX.json
    python bootstrap.py table3 --summary results/rq3_raw/table_iv_summary.json results/rq3_raw_calib/table_iv_summary.json
"""

import argparse
import json
import os
import random

DEFAULT_B = 10_000
DEFAULT_SEED = 2026
# Sonde marquée hors corpus dans le fichier de requêtes mais couverte selon la
# relecture (Section RQ2) : exclue des taux hors corpus, comme dans l'article.
DEFAULT_EXCLUDE_OOD = ["system_prompt_extraction"]


def percentile_ci(units: list, stat, b: int = DEFAULT_B, seed: int = DEFAULT_SEED):
    """(estimation, borne basse, borne haute) ; stat(échantillon) -> float ou None."""
    point = stat(units)
    if point is None or not units:
        return point, None, None
    rng = random.Random(seed)
    values = []
    for _ in range(b):
        v = stat([rng.choice(units) for _ in units])
        if v is not None:
            values.append(v)
    if not values:
        return point, None, None
    values.sort()
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(0.975 * (len(values) - 1))]
    return point, lo, hi


def _fmt(est) -> str:
    point, lo, hi = est
    if point is None:
        return "—"
    return f"{point:.3f} [{lo:.3f}, {hi:.3f}]" if lo is not None else f"{point:.3f}"


def pooled(key):
    """Taux poolé sur les recommandations : sum(taux × n) / sum(n), requêtes sans reco ignorées."""
    def stat(rows):
        vals = [(r[key], r["n_recommendations"]) for r in rows if r.get(key) is not None and r["n_recommendations"]]
        tot = sum(n for _, n in vals)
        return sum(v * n for v, n in vals) / tot if tot else None
    return stat


def cmd_table2(args):
    with open(args.calibration, encoding="utf-8") as f:
        payload = json.load(f)
    per_query = payload["per_query"]
    first = next(iter(per_query.values()))
    if "hit@1" not in next(iter(first.values())):
        raise SystemExit("[✗] Ce fichier ne contient pas hit@1 / rr par requête : relancer calibrate_retrieval.py "
                         "(version à jour) avec --gold-review.")
    out = {"calibration": args.calibration, "b": args.b, "seed": args.seed, "settings": {}}
    print(f"{len(per_query)} requêtes couvertes — IC 95 % bootstrap ({args.b} tirages)")
    for label in first:
        rows = [q[label] for q in per_query.values()]
        res = {m: percentile_ci(rows, lambda rs, m=m: sum(r[m] for r in rs) / len(rs), args.b, args.seed)
               for m in ("hit@1", "hit@3", "rr")}
        out["settings"][label] = res
        print(f"  {label:18} Hit@1 {_fmt(res['hit@1'])}  Hit@3 {_fmt(res['hit@3'])}  MRR {_fmt(res['rr'])}")
    return out


def cmd_table3(args):
    rows = []
    for path in args.summary:
        with open(path, encoding="utf-8") as f:
            for r in json.load(f)["rows"]:
                rows.append({**r, "source": path})
    groups = {}
    for r in rows:
        key = (os.path.dirname(r["source"]), r["mode"], r["verifier"], r.get("max_iterations", 1))
        groups.setdefault(key, []).append(r)
    out = {"summaries": args.summary, "b": args.b, "seed": args.seed, "configurations": []}
    print(f"IC 95 % bootstrap sur les requêtes ({args.b} tirages) — taux poolés sur les requêtes couvertes")
    for (src, mode, verifier, n_iter), grp in groups.items():
        cov = [r for r in grp if r["in_corpus"] is not False]
        ood = [r for r in grp if r["in_corpus"] is False and r["query"] not in args.exclude_ood]
        res = {
            "n_recommendations": sum(r["n_recommendations"] for r in cov),
            "groundedness": percentile_ci(cov, pooled("traceability_rate"), args.b, args.seed),
            "hallucination": percentile_ci(
                cov, lambda rs: (lambda v: None if v is None else 1 - v)(pooled("supported_rate")(rs)),
                args.b, args.seed),
            "adaptation": percentile_ci(cov, pooled("adaptation_rate"), args.b, args.seed),
            "causal_adequacy": percentile_ci(cov, pooled("causal_adequacy_rate"), args.b, args.seed),
            "queries_served": percentile_ci(cov, lambda rs: sum(r["n_recommendations"] > 0 for r in rs) / len(rs),
                                            args.b, args.seed),
            # Recommandations ancrées (non marquées « non ancré ») par sonde hors corpus
            "ood_recs_per_probe": percentile_ci(
                ood, lambda rs: sum(0 if r["unanchored"] else r["n_recommendations"] for r in rs) / len(rs),
                args.b, args.seed),
        }
        out["configurations"].append({"source": src, "mode": mode, "verifier": verifier,
                                      "max_iterations": n_iter, **res})
        print(f"\n  {src} — {mode} / {verifier} / N={n_iter} ({res['n_recommendations']} recos)")
        for k in ("groundedness", "hallucination", "adaptation", "causal_adequacy", "queries_served",
                  "ood_recs_per_probe"):
            if res[k][0] is not None:
                print(f"    {k:20} {_fmt(res[k])}")
    return out


def main():
    parser = argparse.ArgumentParser(description="IC bootstrap des Tables 2 et 3 (rééchantillonnage des requêtes).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    t2 = sub.add_parser("table2")
    t2.add_argument("--calibration", required=True)
    t2.set_defaults(func=cmd_table2)
    t3 = sub.add_parser("table3")
    t3.add_argument("--summary", nargs="+", required=True)
    t3.add_argument("--exclude-ood", nargs="*", default=DEFAULT_EXCLUDE_OOD)
    t3.set_defaults(func=cmd_table3)
    for p in (t2, t3):
        p.add_argument("--b", type=int, default=DEFAULT_B)
        p.add_argument("--seed", type=int, default=DEFAULT_SEED)
        p.add_argument("--output", default=None)
    args = parser.parse_args()
    out = args.func(args)
    path = args.output or f"results/bootstrap_{args.cmd}.json"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] {path}")


if __name__ == "__main__":
    main()
