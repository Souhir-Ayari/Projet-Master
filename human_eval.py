"""
human_eval.py
--------------
Évaluation humaine des recommandations de la Table 3 (consigne du 17/10).

export  Pour chaque configuration de la Table 3, tire au plus N (=10)
        recommandations finales parmi les requêtes couvertes (toutes s'il y en
        a moins). Une même recommandation (même requête, même texte) produite
        par plusieurs configurations n'est notée qu'une fois. Chaque
        évaluateur reçoit sa propre fiche, dans un ordre aléatoire, SANS la
        configuration : il voit la description de l'attaque, la
        recommandation et la mitigation citée (même format pour toutes ; « no
        cited mitigation » sinon). La correspondance item -> configurations est
        écrite dans un fichier clé, à ne pas montrer aux évaluateurs.
        Une configuration sans recommandation est notée « N/A — 0 served ».

score   Lit la clé et les fiches remplies : moyenne et écart-type par
        configuration pour l'utilité, la justesse et l'applicabilité (Likert
        1-5) et part de « would act on this » ; accord inter-évaluateurs
        (alpha de Krippendorff, intervalle) ; comparaisons appariées par
        requête (Wilcoxon contre la configuration de référence, Friedman sur
        les requêtes servies par toutes) ; ligne LaTeX de la colonne Human.

Usage :
    python human_eval.py export --config "No retrieval=results/rq3_raw:no_retrieval|lexical" \\
        "Labels, cal.=results/rq3_raw_calib:retrieval_loop|labels" ... --raters 3
    python human_eval.py score --key results/human_eval/key.json --sheets results/human_eval/sheet_rater1.csv ...
"""

import argparse
import csv
import glob
import json
import os
import random
import statistics

from remediation import _cited_indexes

SCALES = ("usefulness", "soundness", "actionability")
SHEET_FIELDS = ["item", "attack", "recommendation", "cited_mitigation",
                "usefulness", "soundness", "actionability", "would_act", "comment"]


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def parse_config(spec: str) -> tuple[str, str, str]:
    label, rest = spec.split("=", 1)
    directory, key = rest.rsplit(":", 1)
    return label.strip(), directory.strip(), key.strip()


def cited_mitigation(rec: dict, eligible: list[dict]) -> str:
    idx = rec.get("cited")
    if idx is None:
        cands = [i for i in _cited_indexes(rec.get("cited_cases")) if 0 <= i < len(eligible)]
        cands = [i for i in cands if eligible[i].get("mitigation_summary")]
        idx = cands[0] if cands else None
    if idx is None or not (0 <= idx < len(eligible)) or not eligible[idx].get("mitigation_summary"):
        return "no cited mitigation"
    return eligible[idx]["mitigation_summary"]


def collect(directory: str, key: str) -> list[dict]:
    """Recommandations finales de la configuration, requêtes couvertes seulement."""
    out = []
    for path in sorted(glob.glob(os.path.join(directory, "remediation_*.json"))):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if record["query"].get("in_corpus") is False:
            continue
        run = record["runs"].get(key)
        if run is None:
            raise SystemExit(f"[✗] {key!r} absent de {path} (clés : {', '.join(record['runs'])})")
        threshold = record["retrieval"]["threshold"]
        eligible = [c for c in record["retrieval"]["cases"] if c.get("similarity_score", 0) >= threshold]
        for rec in run["final_plan"]:
            action = (rec.get("action") or "").strip()
            if action:
                out.append({"query": record["query"]["name"], "attack": record["query"]["attack_summary"],
                            "recommendation": action, "cited_mitigation": cited_mitigation(rec, eligible)})
    return out


def cmd_export(args):
    rng = random.Random(args.seed)
    configs = [parse_config(c) for c in args.config]
    items, key, served = {}, {}, {}
    for label, directory, run_key in configs:
        recs = collect(directory, run_key)
        served[label] = len(recs)
        chosen = recs if len(recs) <= args.per_config else rng.sample(recs, args.per_config)
        for r in chosen:
            ident = (r["query"], " ".join(r["recommendation"].lower().split()))
            if ident not in items:
                items[ident] = r
            key.setdefault(ident, []).append(label)
        print(f"  {label:32} {len(recs):3} recommandation(s) finale(s) -> {len(chosen)} à noter"
              + ("   [N/A — 0 served]" if not recs else ""))

    ids = rng.sample(range(100, 1000), len(items))
    coded = {f"R{i}": (ident, items[ident]) for i, ident in zip(ids, items)}
    os.makedirs(args.output_dir, exist_ok=True)
    key_path = os.path.join(args.output_dir, "key.json")
    with open(key_path, "w", encoding="utf-8") as f:
        json.dump({"seed": args.seed, "per_config": args.per_config, "configs": [c[0] for c in configs],
                   "served": served,
                   "items": {code: {"query": item["query"], "configs": key[ident],
                                    "recommendation": item["recommendation"]}
                             for code, (ident, item) in coded.items()}},
                  f, indent=2, ensure_ascii=False)
    for k in range(1, args.raters + 1):
        order = list(coded)
        random.Random(args.seed * 100 + k).shuffle(order)
        path = os.path.join(args.output_dir, f"sheet_rater{k}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SHEET_FIELDS, delimiter=";")
            w.writeheader()
            for code in order:
                item = coded[code][1]
                w.writerow({"item": code, "attack": item["attack"], "recommendation": item["recommendation"],
                            "cited_mitigation": item["cited_mitigation"]})
        print(f"[✓] {path}")
    print(f"[✓] {len(coded)} items uniques ; clé (ne pas montrer aux évaluateurs) : {key_path}")
    print("    Consignes : noter chaque ligne de 1 à 5 (usefulness = utile contre CETTE attaque ; soundness ="
          " techniquement correcte ; actionability = applicable telle quelle), would_act = o / n.")


# --------------------------------------------------------------------------- #
# score
# --------------------------------------------------------------------------- #
def read_sheet(path: str) -> dict:
    from audit_false_positives import read_csv_rows
    out = {}
    for r in read_csv_rows(path):
        vals = {}
        for s in SCALES:
            v = (r.get(s) or "").strip()
            if v:
                if v not in {"1", "2", "3", "4", "5"}:
                    raise SystemExit(f"[✗] {path}, item {r['item']} : {s} = {v!r} (attendu 1 à 5)")
                vals[s] = int(v)
        act = (r.get("would_act") or "").strip().lower()
        if act:
            vals["would_act"] = act in ("o", "oui", "y", "yes", "1")
        out[r["item"]] = vals
    return out


def krippendorff_interval(units: list[list[float]]) -> float | None:
    """Alpha de Krippendorff (métrique intervalle) ; units = valeurs des évaluateurs par item (≥ 2 utiles)."""
    units = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in units)
    if n < 2:
        return None
    d_o = sum(sum((a - b) ** 2 for i, a in enumerate(u) for j, b in enumerate(u) if i != j) / (len(u) - 1)
              for u in units) / n
    values = [v for u in units for v in u]
    d_e = sum((a - b) ** 2 for i, a in enumerate(values) for j, b in enumerate(values) if i != j) / (n * (n - 1))
    return None if d_e == 0 else 1 - d_o / d_e


def _stats():
    try:
        from scipy import stats
        return stats
    except ImportError:
        return None


def cmd_score(args):
    with open(args.key, encoding="utf-8") as f:
        key = json.load(f)
    sheets = [read_sheet(p) for p in args.sheets]
    configs = key["configs"]
    reference = args.reference or configs[-1]
    stats = _stats()
    result = {"key": args.key, "sheets": args.sheets, "reference": reference, "configs": {}, "agreement": {},
              "paired": {}}

    # Moyennes par configuration (toutes les notes de tous les évaluateurs)
    print(f"{len(key['items'])} items, {len(sheets)} évaluateur(s)")
    for label in configs:
        codes = [c for c, it in key["items"].items() if label in it["configs"]]
        if not codes:
            result["configs"][label] = {"served": key["served"].get(label, 0), "na": "N/A — 0 served"}
            print(f"  {label:32} N/A — 0 served")
            continue
        res = {"served": key["served"].get(label, 0), "n_items": len(codes)}
        line = []
        for s in SCALES + ("would_act",):
            vals = [sh[c][s] for sh in sheets for c in codes if s in sh.get(c, {})]
            if not vals:
                continue
            vals = [float(v) for v in vals]
            mean = statistics.mean(vals)
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            res[s] = {"mean": round(mean, 2), "sd": round(sd, 2), "n": len(vals)}
            line.append(f"{s} {mean:.2f}±{sd:.2f}" if s != "would_act" else f"would act {mean:.0%}")
        result["configs"][label] = res
        print(f"  {label:32} n={len(codes):2}  " + "  ".join(line))

    # Accord inter-évaluateurs
    if len(sheets) >= 2:
        for s in SCALES:
            units = [[float(sh[c][s]) for sh in sheets if s in sh.get(c, {})] for c in key["items"]]
            a = krippendorff_interval(units)
            result["agreement"][s] = None if a is None else round(a, 3)
            print(f"  alpha de Krippendorff (intervalle) {s:13} = {'—' if a is None else f'{a:.2f}'}")

    # Comparaisons appariées par requête (moyenne des notes de la requête)
    def per_query(label, s):
        by_q = {}
        for c, it in key["items"].items():
            if label in it["configs"]:
                for sh in sheets:
                    if s in sh.get(c, {}):
                        by_q.setdefault(it["query"], []).append(sh[c][s])
        return {q: statistics.mean(v) for q, v in by_q.items()}

    for s in SCALES:
        ref = per_query(reference, s)
        result["paired"][s] = {}
        for label in configs:
            if label == reference:
                continue
            other = per_query(label, s)
            common = sorted(set(ref) & set(other))
            entry = {"n_queries": len(common)}
            if len(common) >= 2 and stats is not None:
                x, y = [ref[q] for q in common], [other[q] for q in common]
                if any(a != b for a, b in zip(x, y)):
                    w = stats.wilcoxon(x, y)
                    entry.update({"wilcoxon_stat": float(w.statistic), "p": float(w.pvalue)})
            result["paired"][s][label] = entry
        served_by_all = set.intersection(*[set(per_query(l, s)) for l in configs if per_query(l, s)]) \
            if any(per_query(l, s) for l in configs) else set()
        active = [l for l in configs if per_query(l, s)]
        if len(served_by_all) >= 2 and len(active) >= 3 and stats is not None:
            fr = stats.friedmanchisquare(*[[per_query(l, s)[q] for q in sorted(served_by_all)] for l in active])
            result["paired"][s]["friedman"] = {"n_queries": len(served_by_all), "chi2": float(fr.statistic),
                                               "p": float(fr.pvalue)}
        print(f"  {s} : Wilcoxon contre « {reference} » — "
              + ", ".join(f"{l}: n={e['n_queries']}" + (f", p={e['p']:.3f}" if 'p' in e else "")
                          for l, e in result["paired"][s].items() if l != "friedman")
              + (f" ; Friedman n={result['paired'][s]['friedman']['n_queries']}, "
                 f"p={result['paired'][s]['friedman']['p']:.3f}" if "friedman" in result["paired"][s] else ""))
    if stats is None:
        print("  [⚠] scipy absent : tests de Wilcoxon et Friedman non calculés (pip install scipy)")

    # Cellule LaTeX de la colonne Human (utilité moyenne ± écart-type)
    cells = {}
    for label, res in result["configs"].items():
        cells[label] = (r"N/A\textsuperscript{a}" if "na" in res else
                        f"{res['usefulness']['mean']:.1f} $\\pm$ {res['usefulness']['sd']:.1f}"
                        if "usefulness" in res else "--")
    result["latex_human_column"] = cells
    out = args.output or os.path.join(os.path.dirname(args.key), "human_eval_score.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("\nColonne Human (utilité moyenne ± écart-type) :")
    for label, cell in cells.items():
        print(f"  {label:32} {cell}")
    print(f"\n[✓] {out}")


def main():
    parser = argparse.ArgumentParser(description="Évaluation humaine des recommandations (Table 3).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--config", nargs="+", required=True,
                   help='"Libellé=dossier_du_run:clé_du_run", ex. "Labels, cal.=results/rq3_raw_calib:retrieval_loop|labels"')
    e.add_argument("--per-config", type=int, default=10)
    e.add_argument("--raters", type=int, default=3)
    e.add_argument("--seed", type=int, default=17)
    e.add_argument("--output-dir", default="results/human_eval")
    e.set_defaults(func=cmd_export)
    s = sub.add_parser("score")
    s.add_argument("--key", required=True)
    s.add_argument("--sheets", nargs="+", required=True)
    s.add_argument("--reference", default=None, help="configuration de référence des tests appariés (défaut : la dernière)")
    s.add_argument("--output", default=None)
    s.set_defaults(func=cmd_score)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
