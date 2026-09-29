"""
rq1_table.py
--------------
Assemble la Table I du papier (RQ1 : GLiNER vs variantes Mistral) à partir
des fichiers eval_<méthode>.json écrits par main.py, une méthode par run :

    python main.py --pdf paper.pdf --ground-truth gt.json --only gliner --output-dir results/rq1
    python main.py --pdf paper.pdf --ground-truth gt.json --only naive  --output-dir results/rq1
    ...
    python rq1_table.py --dir results/rq1

Pourquoi un script séparé : un run Mistral complet dure plusieurs heures sur
CPU. Lancer chaque méthode seule permet de les enchaîner (ou d'en relancer
une seule), mais final_comparison.json ne contient alors que la méthode du
dernier run. Ce script relit les scores de toutes les méthodes du dossier et
vérifie qu'ils portent bien sur le MÊME PDF, le même ground truth et le même
découpage — sans quoi les lignes de la table ne seraient pas comparables.

Écrit table_i.json dans le dossier et affiche les lignes LaTeX à recopier.
"""

import argparse
import glob
import json
import os

# Ordre et libellés des lignes de la Table I du papier.
ROWS = [
    ("gliner_ner", "GLiNER (zero-shot)"),
    ("mistral_naive", "Mistral (naive)"),
    ("mistral_engineered", "Mistral (engineered)"),
    ("mistral_custom", "Mistral (custom)"),
    ("mistral_topic", "Mistral (topic, ours)"),
]


def main():
    parser = argparse.ArgumentParser(description="Assemble la Table I (RQ1) depuis eval_*.json.")
    parser.add_argument("--dir", default="results/rq1")
    args = parser.parse_args()

    evals = {}
    for path in sorted(glob.glob(os.path.join(args.dir, "eval_*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        evals[data["method"]] = data
    if not evals:
        raise SystemExit(f"[✗] Aucun eval_*.json dans {args.dir} — lancer main.py avec --ground-truth d'abord.")

    setups = {(e.get("pdf"), e.get("ground_truth"), e.get("n_chunks")) for e in evals.values()}
    if len(setups) > 1:
        print("[⚠] Les runs ne portent pas tous sur le même PDF / ground truth / découpage :")
        for method, e in evals.items():
            print(f"    {method}: {e.get('pdf')}, {e.get('ground_truth')}, {e.get('n_chunks')} chunks")
        print("    Les lignes ne sont pas comparables : relancer les méthodes concernées.\n")

    print(f"{'Méthode':24} {'P':>6} {'R':>6} {'F1':>6} {'Halluc.':>8} {'TP':>4} {'FP':>4} {'FN':>4}"
          f" | {'F1 relâché':>10}  run")
    latex, table = [], []
    for method, label in ROWS:
        e = evals.get(method)
        if e is None:
            print(f"{label:24} {'— pas encore lancé':>40}")
            latex.append(f"{label} & \\textcolor{{red}}{{TBD}} & \\textcolor{{red}}{{TBD}} "
                         f"& \\textcolor{{red}}{{TBD}} & \\textcolor{{red}}{{TBD}} \\\\")
            continue
        print(f"{label:24} {e['precision']:>6.3f} {e['recall']:>6.3f} {e['f1']:>6.3f} "
              f"{e['hallucination_rate']:>8.3f} {e['true_positives']:>4} {e['false_positives']:>4} "
              f"{e['false_negatives']:>4} | {e.get('relaxed_f1', float('nan')):>10.3f}  "
              f"{e.get('timestamp', '')[:16]}")
        latex.append(f"{label} & {e['precision']:.3f} & {e['recall']:.3f} & {e['f1']:.3f} "
                     f"& {e['hallucination_rate']:.3f} \\\\")
        table.append({"row": label, **{k: e[k] for k in (
            "method", "precision", "recall", "f1", "hallucination_rate",
            "true_positives", "false_positives", "false_negatives",
            "n_predicted", "n_ground_truth")},
            **{k: e.get(k) for k in ("relaxed_precision", "relaxed_recall", "relaxed_f1")},
            "timestamp": e.get("timestamp")})

    out = os.path.join(args.dir, "table_i.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"setup": sorted(map(str, setups)), "rows": table}, f, indent=2, ensure_ascii=False)
    print("\nLignes LaTeX (Table I) :")
    print("\n".join(latex))
    print(f"\n[✓] {out}")


if __name__ == "__main__":
    main()
