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

    # Une seule méthode par run (RQ1 : une ligne de la Table I à la fois),
    # résultats et scores dans un dossier dédié, puis assemblage :
    python main.py --pdf paper.pdf --ground-truth gt.json --only gliner --output-dir results/rq1
    python main.py --pdf paper.pdf --ground-truth gt.json --only topic --output-dir results/rq1
    python rq1_table.py --dir results/rq1

    # Prompt spécifique au sujet "attaques de chaîne d'approvisionnement / backdoors"
    # (utile pour un document type XZ Utils, SolarWinds, Log4Shell) :
    python main.py --pdf rapport.pdf --ground-truth ground_truth_xz_backdoor.json \\
        --variants naive engineered topic
"""

import argparse
import datetime
import json
import os

from config import CYBER_ENTITY_LABELS, DEFAULT_DOMAIN, TOPIC_DOMAINS, topic_config
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
    global OUTPUT_DIR
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
        "'topic' utilise un prompt + une taxonomie spécifiques au sujet du document "
        "(voir --domain).",
    )
    parser.add_argument(
        "--domain",
        default=DEFAULT_DOMAIN,
        choices=sorted(TOPIC_DOMAINS),
        help="Sujet du document analysé, utilisé UNIQUEMENT par la variante "
        "'topic' : 'llm' (menaces sur les LLM — injection de prompt, jailbreak, "
        "fuite de données ; défaut) ou 'supply_chain' (chaîne "
        "d'approvisionnement logicielle : XZ Utils, SolarWinds, Log4Shell). "
        "Les autres variantes utilisent la taxonomie générique et servent de "
        "point de comparaison indépendant du sujet.",
    )
    parser.add_argument(
        "--only",
        default=None,
        choices=["gliner", "naive", "naive_schema", "engineered", "custom", "topic"],
        help="Lance UNE seule méthode (GLiNER ou une variante Mistral) au lieu "
        "de GLiNER + toutes les --variants. Un run complet dure plusieurs "
        "heures sur CPU : une méthode par run permet de les enchaîner "
        "séparément, chacune enregistrant ses scores dans eval_<méthode>.json "
        "(assemblés ensuite par rq1_table.py).",
    )
    parser.add_argument(
        "--gliner-taxonomy",
        default="domain",
        choices=["domain", "generic"],
        help="Labels donnés à GLiNER : 'domain' (défaut) = taxonomie du "
        "--domain, la même que la variante 'topic' ; 'generic' = labels cyber "
        "classiques (IP, hash, CVE...), l'ancien comportement. Sur un papier "
        "d'attaques LLM, les labels génériques ne décrivent presque aucune "
        "entité du ground truth : GLiNER était évalué sur une tâche qu'on ne "
        "lui avait pas demandée.",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Dossier des résultats (défaut : results). Un dossier par "
        "expérience évite qu'un run écrase les fichiers d'un autre corpus.",
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

    OUTPUT_DIR = args.output_dir
    run_gliner = args.only in (None, "gliner")
    variants = [] if args.only == "gliner" else ([args.only] if args.only else args.variants)

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
    gliner = None
    if run_gliner:
        print("\n[2/4] CAS 1 : extraction NER pure (GLiNER)")
        gliner_labels = (
            topic_config(args.domain)["labels"]
            if args.gliner_taxonomy == "domain"
            else CYBER_ENTITY_LABELS
        )
        print(f"      labels GLiNER ({args.gliner_taxonomy}) : {len(gliner_labels)}")
        gliner = GLiNERExtractor(labels=gliner_labels)
        gliner_output = gliner.extract_from_chunks(chunks)
        gliner_output["taxonomy"] = args.gliner_taxonomy
        save_json(gliner_output, "case1_gliner.json")
        all_results["gliner_ner"] = gliner_output

    # --- 3. CAS 2 : Mistral prompt-based (variantes choisies) ----------
    if variants:
        print(
            f"\n[3/4] CAS 2 : extraction prompt-based (Mistral 7B, backend={args.backend})"
        )
    mistral = MistralExtractor(backend=args.backend) if variants or args.hybrid else None

    # Récupère le besoin utilisateur une seule fois si la variante 'custom' est demandée
    user_need = args.user_need
    if "custom" in variants and not user_need:
        print("\n" + "-" * 70)
        user_need = input(
            "👉 Décrivez précisément ce que vous voulez extraire du document\n"
            '   (ex: "Extrais uniquement les CVE et les logiciels/versions vulnérables cités") :\n> '
        ).strip()
        print("-" * 70)

    for variant in variants:
        need = user_need if variant == "custom" else None
        result = mistral.extract_from_chunks(
            chunk_texts, prompt_variant=variant, user_need=need, domain=args.domain
        )
        print(
            f"\n--- CAS 2 - Mistral prompt '{variant}' ---"
            + (f" (besoin : {need})" if variant == "custom" else "")
            + (f" (domaine : {args.domain})" if variant == "topic" else "")
        )
        save_json(result, f"case2_mistral_{variant}.json")
        all_results[f"mistral_{variant}"] = result

    # --- 4. (option) Pipeline hybride -----------------------------------
    if args.hybrid:
        from hybrid_extractor import HybridExtractor

        print("\n[4/4] CAS HYBRIDE : GLiNER -> validation Mistral")
        hybrid = HybridExtractor(gliner=gliner or GLiNERExtractor(), mistral=mistral)
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
            # Scores de CHAQUE méthode dans leur propre fichier : avec --only,
            # final_comparison.json ne contient que la méthode du dernier
            # run ; ces fichiers permettent d'assembler la Table I ensuite.
            save_json(
                {
                    **ev_dict,
                    "pdf": os.path.basename(args.pdf),
                    "ground_truth": args.ground_truth,
                    "domain": args.domain,
                    "n_chunks": len(chunks),
                    "timestamp": datetime.datetime.now().isoformat(),
                },
                f"eval_{method_name}.json",
            )

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
