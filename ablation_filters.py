"""
ablation_filters.py
---------------------
Table II du papier (RQ1) : contribution de chaque filtre de Layer 1, ajoutés
un par un, SANS relancer Mistral.

Les filtres s'appliquent APRÈS la génération : main.py enregistre la réponse
brute du modèle pour chaque chunk (raw_model_output dans
case2_mistral_<variante>.json). Ce script rejoue MistralExtractor.extract —
le même code que le pipeline — sur ces réponses enregistrées, avec un
sous-ensemble de filtres actifs. Toutes les lignes de la table portent ainsi
sur les MÊMES sorties du modèle : seule la configuration des filtres change,
ce qui isole leur effet (une ablation qui relancerait Mistral mélangerait
l'effet des filtres et la variabilité de génération), en quelques secondes
au lieu d'une heure de génération par ligne.

Contrôle de fidélité : la ligne "Full system" doit retrouver exactement les
scores de eval_mistral_<variante>.json quand ce fichier est présent.

Usage :
    python ablation_filters.py --pdf files/Prompt-Injection.pdf \\
        --ground-truth ground_truth_prompt_injection.json \\
        --case results/rq1_prompt_injection/case2_mistral_topic.json
"""

import argparse
import contextlib
import io
import json
import os

from config import DEFAULT_DOMAIN
from evaluator import evaluate
from mistral_extractor import FILTER_NAMES, MistralExtractor
from pdf_extractor import extract_text_from_pdf

# Lignes cumulatives de la Table II : (libellé, filtres actifs).
# Les quatre premiers filtres sont ceux décrits au §III-B du papier ; la
# dernière ligne ajoute les contrôles restants du code (format attendu,
# bruit bibliographique, et pour custom les catégories jugées pertinentes).
ROWS = [
    ("No filters (raw output)", []),
    ("+ label whitelist", ["label_whitelist"]),
    ("+ span-length filter", ["label_whitelist", "span_length"]),
    ("+ exemplar-leakage filter", ["label_whitelist", "span_length", "template_leak"]),
    ("+ filler-value filter", ["label_whitelist", "span_length", "template_leak", "filler"]),
    ("Full system (+ format, citation noise)", list(FILTER_NAMES)),
]


def replay(case: dict, enabled: set, domain: str) -> list[dict]:
    """Rejoue extract_from_chunks sur les réponses brutes enregistrées, filtres `enabled` actifs."""
    variant = case["method"].replace("mistral_prompt_", "")
    raws = list(case["raw_model_output"])
    extractor = MistralExtractor.__new__(MistralExtractor)  # sans backend : aucun appel au modèle
    extractor.backend = "replay"
    extractor.enabled_filters = enabled
    answers = iter(raws)
    extractor._generate = lambda prompt: next(answers)
    with contextlib.redirect_stdout(io.StringIO()):  # avertissements par chunk : déjà vus au run
        result = extractor.extract_from_chunks(
            [""] * len(raws), prompt_variant=variant, user_need=case.get("user_need") or "", domain=domain
        )
    return result["entities"]


def main():
    parser = argparse.ArgumentParser(description="Table II : ablation des filtres Layer 1 sans relancer Mistral.")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--case", required=True, help="case2_mistral_<variante>.json d'un run de main.py")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    args = parser.parse_args()

    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)
    with open(args.ground_truth, encoding="utf-8") as f:
        gt = json.load(f)["entities"]
    text = extract_text_from_pdf(args.pdf, verbose=False)

    out_dir = os.path.dirname(args.case) or "."
    print(f"Réponses rejouées : {args.case} ({len(case['raw_model_output'])} chunks, {case['method']})\n")
    print(f"{'Configuration':42} {'#pred':>5} {'P':>6} {'R':>6} {'F1':>6} {'Halluc.':>8} | {'F1 relâché':>10}")
    rows, latex = [], []
    for label, filters in ROWS:
        ev = evaluate(label, replay(case, set(filters), args.domain), gt, text).to_dict()
        rows.append({"row": label, "filters": filters, **ev})
        print(f"{label:42} {ev['n_predicted']:>5} {ev['precision']:>6.3f} {ev['recall']:>6.3f} "
              f"{ev['f1']:>6.3f} {ev['hallucination_rate']:>8.3f} | {ev['relaxed_f1']:>10.3f}")
        latex.append(f"{label} & {ev['precision']:.3f} & {ev['recall']:.3f} & {ev['f1']:.3f} "
                     f"& {ev['hallucination_rate']:.3f} \\\\")

    eval_path = os.path.join(out_dir, "eval_" + case["method"].replace("_prompt", "") + ".json")
    if os.path.exists(eval_path):
        with open(eval_path, encoding="utf-8") as f:
            ref = json.load(f)
        full = rows[-1]
        same = all(abs(full[k] - ref[k]) < 1e-4 for k in ("precision", "recall", "f1", "hallucination_rate"))
        print(f"\nContrôle de fidélité vs {eval_path} : "
              + ("✓ identique" if same else f"✗ DIFFÉRENT (P {ref['precision']}, R {ref['recall']}, F1 {ref['f1']})"
                 " — le texte ou le ground truth ont changé depuis ce run"))

    out = os.path.join(out_dir, f"table_ii_{case['method'].replace('mistral_prompt_', '')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"case": args.case, "ground_truth": args.ground_truth, "rows": rows}, f, indent=2, ensure_ascii=False)
    print("\nLignes LaTeX (Table II) :\n" + "\n".join(latex))
    print(f"\n[✓] {out}")


if __name__ == "__main__":
    main()
