"""
main.py
-------
Orchestrateur de l'expérience complète :

  1. Charge un PDF et en extrait le texte.
  2. CAS 1 : extraction NER pure via GLiNER          -> JSON dans le terminal.
  3. CAS 2 : extraction prompt-based via Mistral 7B, avec jusqu'à 3 variantes :
       - "naive"      : prompt basique, sert de référence basse
       - "engineered" : prompt optimisé anti-hallucination, labels génériques
       - "custom"     : prompt piloté par un besoin SPÉCIFIQUE exprimé par
                         l'utilisateur (plus ciblé que le NER généraliste),
                         fourni via --user-need ou saisi de manière interactive
  4. (option) CAS HYBRIDE : GLiNER + validation Mistral.
  5. Si un ground truth est fourni : calcule Precision/Recall/F1 et taux
     d'hallucination pour CHAQUE méthode, puis affiche le classement final
     et le "combo idéal".

Usage :
    python main.py --pdf rapport.pdf
    python main.py --pdf rapport.pdf --ground-truth ground_truth.json
    python main.py --pdf rapport.pdf --ground-truth ground_truth.json --hybrid
    python main.py --pdf rapport.pdf --backend transformers

    # Extraction pilotée par un besoin utilisateur spécifique (CAS 2 "custom") :
    python main.py --pdf rapport.pdf --variants naive engineered custom \\
        --user-need "Extrais uniquement les CVE et les logiciels/versions vulnérables cités"

    # Ou sans --user-need : le programme vous le demandera à l'exécution.
    python main.py --pdf rapport.pdf --variants custom

    # Prompt spécifique au sujet "attaques de chaîne d'approvisionnement / backdoors"
    # (utile pour un document type XZ Utils, SolarWinds, Log4Shell) :
    python main.py --pdf rapport.pdf --ground-truth ground_truth_xz_backdoor.json \\
        --variants naive engineered topic
"""

import argparse
import datetime
import json
import os

from evaluator import compare_methods, evaluate
from gliner_extractor import GLiNERExtractor
from mistral_extractor import MistralExtractor
from pdf_extractor import chunk_text, extract_text_from_pdf

OUTPUT_DIR = "results"


def save_json(data: dict, filename: str, add_timestamp: bool = False):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if add_timestamp:
        base, ext = os.path.splitext(filename)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
        filename = f"{base}_{timestamp}{ext}"
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if isinstance(data, dict) and "entities" in data:
        n_entities = len(data.get("entities", []))
        print(f"[✔] {n_entities} entité(s) extraite(s) -> {path}")
    else:
        print(f"[✔] JSON sauvegardé -> {path}")
    return path


def save_to_history(data: dict, filename: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = []
    history.append(
        {
            "timestamp": datetime.datetime.now().isoformat(),
            "result": data,
        }
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"[✔] Historique mis à jour -> {path}")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Expérience GLiNER vs Mistral 7B (prompt-based) - extraction cybersécurité"
    )
    parser.add_argument("--pdf", required=True, help="Chemin vers le PDF d'entrée")
    parser.add_argument(
        "--ground-truth",
        default=None,
        help="Chemin vers un JSON de ground truth annoté",
    )
    parser.add_argument(
        "--backend",
        default="ollama",
        choices=["ollama", "transformers"],
        help="Backend pour Mistral 7B",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Active aussi le pipeline hybride GLiNER+Mistral",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["naive", "engineered", "custom", "topic"],
        choices=["naive", "naive_schema", "engineered", "custom", "topic"],
        help="Variantes de prompt à tester pour le CAS 2 (Mistral). "
        "'naive_schema' isole la variable 'schéma JSON' seule (sans règles "
        "anti-hallucination) pour une comparaison propre naive -> naive_schema -> engineered. "
        "'custom' permet de spécifier un besoin d'extraction précis (voir --user-need). "
        "'topic' utilise un prompt + une taxonomie spécifiques aux attaques de chaîne "
        "d'approvisionnement logicielle / backdoors (XZ Utils, SolarWinds, Log4Shell).",
    )
    parser.add_argument(
        "--user-need",
        default=None,
        help="Besoin d'extraction spécifique en langage naturel, utilisé uniquement "
        "si 'custom' est présent dans --variants. Ex: "
        '"Extrais uniquement les CVE et les IP mentionnées". '
        "Si non fourni et que 'custom' est demandé, une saisie interactive sera proposée.",
    )
    args = parser.parse_args()

    # --- 1. Extraction du texte ---------------------------------------
    print(f"[1/4] Lecture du PDF : {args.pdf}")
    text = extract_text_from_pdf(args.pdf)
    chunks = chunk_text(
        text
    )  # liste de (start_idx, chunk_texte) -> voir pdf_extractor.chunk_text
    chunk_texts = [
        c for _, c in chunks
    ]  # texte seul, pour Mistral/hybride (n'ont pas besoin des offsets)
    print(f"      -> {len(text)} caractères, {len(chunks)} chunk(s)")

    all_results = {}

    # --- 2. CAS 1 : GLiNER (NER pur) -----------------------------------
    print("\n[2/4] CAS 1 : extraction NER pure (GLiNER)")
    gliner = GLiNERExtractor()
    gliner_output = gliner.extract_from_chunks(chunks)
    save_json(gliner_output, "case1_gliner.json")
    all_results["gliner_ner"] = gliner_output

    # --- 3. CAS 2 : Mistral prompt-based (variantes choisies) ----------
    print(
        f"\n[3/4] CAS 2 : extraction prompt-based (Mistral 7B, backend={args.backend})"
    )
    mistral = MistralExtractor(backend=args.backend)

    # Récupère le besoin utilisateur une seule fois si la variante 'custom' est demandée
    user_need = args.user_need
    if "custom" in args.variants and not user_need:
        print("\n" + "-" * 70)
        user_need = input(
            "👉 Décrivez précisément ce que vous voulez extraire du document\n"
            '   (ex: "Extrais uniquement les CVE et les logiciels/versions vulnérables cités") :\n> '
        ).strip()
        print("-" * 70)

    for variant in args.variants:
        need = user_need if variant == "custom" else None
        result = mistral.extract_from_chunks(
            chunk_texts, prompt_variant=variant, user_need=need
        )
        print(
            f"\n--- CAS 2 - Mistral prompt '{variant}' ---"
            + (f" (besoin : {need})" if variant == "custom" else "")
        )
        save_json(result, f"case2_mistral_{variant}.json")
        all_results[f"mistral_{variant}"] = result

    # --- 4. (option) Pipeline hybride -----------------------------------
    if args.hybrid:
        from hybrid_extractor import HybridExtractor

        print("\n[4/4] CAS HYBRIDE : GLiNER -> validation Mistral")
        hybrid = HybridExtractor(gliner=gliner, mistral=mistral)
        hybrid_output = hybrid.extract(
            text if len(chunk_texts) == 1 else chunk_texts[0]
        )
        save_json(hybrid_output, "case3_hybrid.json")
        all_results["hybrid"] = hybrid_output

    # --- 5. Évaluation (si ground truth fourni) -------------------------
    if args.ground_truth:
        print(f"\n{'=' * 70}\nÉVALUATION vs GROUND TRUTH\n{'=' * 70}")
        with open(args.ground_truth, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        ground_truth_entities = gt_data["entities"]

        eval_results = []
        for method_name, result in all_results.items():
            ev = evaluate(method_name, result["entities"], ground_truth_entities, text)
            eval_results.append(ev)

            print(f"\n--- {method_name} ---")
            ev_dict = ev.to_dict()
            print(json.dumps(ev_dict, indent=2, ensure_ascii=False))

        comparison = compare_methods(eval_results)
        print(f"\n{'=' * 70}\nCLASSEMENT FINAL\n{'=' * 70}")
        print(json.dumps(comparison, indent=2, ensure_ascii=False))

        # Sauvegarder la comparaison avec timestamp (version avec historique)
        save_to_history(comparison, "final_comparison_history.json")

        # Sauvegarder aussi une version avec timestamp pour consultation rapide
        save_json(comparison, "final_comparison.json", add_timestamp=True)

    else:
        print(
            "\n[i] Aucun ground truth fourni (--ground-truth) : pas de calcul de F1/hallucination."
        )
        print(
            "    Copiez ground_truth_template.json, annotez-le pour VOTRE pdf, puis relancez avec --ground-truth."
        )


if __name__ == "__main__":
    main()
