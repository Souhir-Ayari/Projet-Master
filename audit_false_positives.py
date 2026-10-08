"""
audit_false_positives.py
--------------------------
Audit manuel des faux positifs de RQ1 : transforme l'explication "le ground
truth est partiel" en MESURE.

Protocole (deux étapes, le jugement reste humain) :

1. Tirage — tire N faux positifs au hasard (graine fixe : tirage
   reproductible, on ne choisit pas les cas) parmi les prédictions d'un run
   comptées fausses par le F1 strict, et écrit un CSV à remplir à la main.
   Chaque ligne donne l'entité, son label et un extrait du texte du papier
   autour de sa première occurrence, pour juger sans rouvrir le PDF.

       python audit_false_positives.py sample --pdf files/Prompt-Injection.pdf \\
           --ground-truth ground_truth_prompt_injection.json \\
           --case results/rq1_prompt_injection/case2_mistral_topic.json

2. Annotation — dans le CSV (s'ouvre dans Excel, séparateur ;), remplir la
   colonne "valide" pour chaque ligne :
       o  = entité légitime du papier, du bon type, absente de l'annotation
       n  = vraie erreur (phrase descriptive, mauvais label, bruit, texte abîmé...)
   et, si utile, la colonne "raison". Décider avec le guide d'annotation du
   ground truth, AVANT de regarder le résultat global.

3. Score — calcule la part de faux positifs valides (avec intervalle de
   confiance de Wilson à 95 %, l'échantillon étant petit) et la précision
   corrigée qu'on en déduit par extrapolation à tous les faux positifs.

       python audit_false_positives.py score --audit results/rq1_prompt_injection/audit_fp_topic.csv

La précision corrigée est une ESTIMATION : la précision rapportée dans la
Table I reste la mesure de référence, et devient une borne inférieure.
"""

import argparse
import csv
import io
import json
import math
import os
import random
import re
import time

from evaluator import _normalize, evaluate, false_positive_entities
from pdf_extractor import extract_text_from_pdf

DEFAULT_N = 30
DEFAULT_SEED = 42
CONTEXT_CHARS = 160
FIELDS = ["id", "entite", "label", "contexte", "valide", "raison"]
YES = {"o", "oui", "y", "yes", "1", "v", "valide"}
NO = {"n", "non", "no", "0", "x"}


def context_of(entity: str, text: str, width: int = CONTEXT_CHARS) -> str:
    """Extrait du texte autour de la première occurrence de l'entité (casse et espaces ignorés)."""
    words = [re.escape(w) for w in entity.split()]
    if not words:
        return ""
    m = re.search(r"\s+".join(words), text, flags=re.IGNORECASE)
    if m is None:
        return "(introuvable tel quel dans le texte extrait)"
    start, end = max(m.start() - width, 0), min(m.end() + width, len(text))
    before = re.sub(r"\s+", " ", text[start:m.start()])
    after = re.sub(r"\s+", " ", text[m.end():end])
    found = re.sub(r"\s+", " ", m.group(0))
    return f"...{before}[[{found}]]{after}..."


def read_csv_rows(path: str) -> list[dict]:
    """
    Relit un CSV annoté à la main. Excel peut le réenregistrer en UTF-8 ou en
    Windows-1252 (« CSV (séparateur : point-virgule) »), avec ; ou , : on
    accepte les deux encodages et les deux séparateurs.
    """
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    header = text.splitlines()[0] if text else ""
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(centre - half, 0.0), min(centre + half, 1.0)


def cmd_sample(args):
    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)
    with open(args.ground_truth, encoding="utf-8") as f:
        gt = json.load(f)["entities"]
    text = extract_text_from_pdf(args.pdf, verbose=False)

    ev = evaluate(case["method"], case["entities"], gt, text).to_dict()
    fps = false_positive_entities(case["entities"], gt)
    assert len(fps) == ev["false_positives"], "incohérence avec evaluator.evaluate"
    n = min(args.n, len(fps))
    sample = random.Random(args.seed).sample(fps, n)

    variant = case["method"].replace("mistral_prompt_", "")
    out_dir = os.path.dirname(args.case) or "."
    out = args.output or os.path.join(out_dir, f"audit_fp_{variant}.csv")
    if os.path.exists(out) and not args.force:
        raise SystemExit(f"[✗] {out} existe déjà (annotations en cours ?) — --force pour l'écraser.")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        w.writeheader()
        for i, e in enumerate(sample, 1):
            w.writerow({"id": i, "entite": e.get("text", ""), "label": e.get("label", ""),
                        "contexte": context_of(e.get("text", ""), text), "valide": "", "raison": ""})

    meta = {"case": args.case, "ground_truth": args.ground_truth, "pdf": args.pdf,
            "method": case["method"], "seed": args.seed, "n_sample": n,
            "n_predicted": ev["n_predicted"], "true_positives": ev["true_positives"],
            "false_positives": ev["false_positives"], "precision": ev["precision"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.splitext(out)[0] + "_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"{case['method']} : {ev['n_predicted']} prédictions, {ev['true_positives']} VP, "
          f"{ev['false_positives']} FP (précision {ev['precision']:.3f})")
    print(f"[✓] {n} faux positifs tirés au hasard (graine {args.seed}) -> {out}")
    print("    Remplir la colonne 'valide' (o / n), puis : "
          f"python audit_false_positives.py score --audit {out}")


def cmd_score(args):
    with open(os.path.splitext(args.audit)[0] + "_meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    rows = read_csv_rows(args.audit)

    valid, invalid, missing = [], [], []
    for r in rows:
        v = _normalize(r.get("valide") or "")
        (valid if v in YES else invalid if v in NO else missing).append(r)
    if missing:
        ids = ", ".join(r["id"] for r in missing)
        raise SystemExit(f"[✗] {len(missing)} ligne(s) sans jugement o/n dans 'valide' : {ids}")

    n, k = len(rows), len(valid)
    share = k / n if n else 0.0
    lo, hi = wilson(k, n)
    tp, fp, n_pred = meta["true_positives"], meta["false_positives"], meta["n_predicted"]

    def corrected(s):
        return (tp + s * fp) / n_pred if n_pred else 0.0

    print(f"{meta['method']} — audit de {n} faux positifs sur {fp}")
    print(f"  valides (absents de l'annotation) : {k}/{n} = {share:.0%}  [IC 95 % Wilson : {lo:.0%} – {hi:.0%}]")
    print(f"  précision rapportée : {meta['precision']:.3f}  ->  corrigée estimée : {corrected(share):.3f}"
          f"  [{corrected(lo):.3f} – {corrected(hi):.3f}]")
    reasons = {}
    for r in invalid:
        key = (r.get("raison") or "").strip().lower() or "(sans raison)"
        reasons[key] = reasons.get(key, 0) + 1
    if invalid:
        print("  vraies erreurs par raison : " + ", ".join(f"{c}× {k_}" for k_, c in sorted(reasons.items(), key=lambda x: -x[1])))

    sentence = (f"A manual audit of {n} randomly sampled false positives of the {meta['method'].replace('mistral_prompt_', '')} "
                f"run found {k} ({share:.0%}; 95% Wilson interval {lo:.0%}--{hi:.0%}) to be valid entities absent "
                f"from the annotation, indicating that the reported precision ({meta['precision']:.3f}) is a lower bound; "
                f"extrapolating this share to all {fp} false positives gives an estimated precision of {corrected(share):.2f}.")
    sentence = sentence.replace("%", r"\%")
    out = os.path.splitext(args.audit)[0] + "_score.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({**meta, "audit": args.audit, "n_audited": n, "n_valid": k, "share_valid": share,
                   "wilson_95": [lo, hi], "corrected_precision": corrected(share),
                   "corrected_precision_ci": [corrected(lo), corrected(hi)],
                   "invalid_reasons": reasons, "latex_sentence": sentence}, f, indent=2, ensure_ascii=False)
    print(f"\nPhrase pour le papier :\n{sentence}\n\n[✓] {out}")


def main():
    parser = argparse.ArgumentParser(description="Audit manuel des faux positifs RQ1.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="tire N faux positifs au hasard dans un CSV à annoter")
    s.add_argument("--pdf", required=True)
    s.add_argument("--ground-truth", required=True)
    s.add_argument("--case", required=True, help="case2_mistral_<variante>.json (ou case1_gliner.json)")
    s.add_argument("--n", type=int, default=DEFAULT_N)
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.add_argument("--output", default=None)
    s.add_argument("--force", action="store_true", help="écraser un CSV existant")
    s.set_defaults(func=cmd_sample)
    c = sub.add_parser("score", help="calcule la part de faux positifs valides d'un CSV annoté")
    c.add_argument("--audit", required=True)
    c.set_defaults(func=cmd_score)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
