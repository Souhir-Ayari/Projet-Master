"""
reclassify_cases.py
---------------------
Redemande UNIQUEMENT la technique ATLAS des cas déjà extraits, sans refaire
les résumés de la Layer 2, et mesure la justesse contre la relecture
(review_cases.py) — avant/après modification du prompt de classification.

Pourquoi : la relecture des 119 cas a montré 47,5 % d'identifiants corrects,
avec des confusions systématiques (jailbreak classé en injection de prompt,
sous-technique "Triggered" presque toujours fausse). La short-list contenait
déjà AML.T0054 : le modèle ne disposait que des NOMS des techniques, sans
leur définition. Le prompt de classification reçoit donc maintenant la
définition officielle ATLAS de chaque technique et une règle de distinction
jailbreak / injection / empoisonnement (config.METHODOLOGY_DOMAIN_CONTEXT).

Deux modes, sur les MÊMES cas, avec le même extrait et le même résumé :
  names        prompt de classification avec les noms seuls (référence)
  definitions  noms + définitions ATLAS + règle de distinction
La justesse de la Layer 2 d'origine (champ category de la table brute) est
rapportée à côté.

Biais à écrire dans le papier : la règle de distinction a été rédigée APRÈS
l'analyse des erreurs sur ces mêmes cas. Elle reprend les définitions ATLAS
et ne cite aucun cas, mais le gain mesuré ici est optimiste ; il doit être
confirmé sur des papers non relus.

Chaque cas est retrouvé dans son extrait d'origine via results/methodology_
<paper>.jsonl (même attack_summary -> chunk_index), puis le PDF est
re-découpé de la même façon que dans build_knowledge.py. À défaut, seul le
résumé est donné au modèle (signalé dans la sortie).

Usage :
    python reclassify_cases.py --table results/knowledge_table_llm_raw.jsonl \\
        --review results/review_knowledge_table_llm.csv \\
        --pdf-dir files files/corpus_llm
    # Tous les cas de la table sont reclassés (la justesse n'est mesurée que
    # sur les cas relus) ; option : --write-table écrit
    # knowledge_table_llm_raw_reclassified.jsonl
    # (+ ses .npz), table toujours 100 % automatique, candidate pour la Table IV.
"""

import argparse
import glob
import json
import os
import shutil
import time
from collections import Counter

import attack_taxonomy
from audit_false_positives import wilson
from config import DEFAULT_DOMAIN, classify_prompt
from jsonl_utils import append_jsonl, read_jsonl, write_jsonl
from knowledge_table import load_table, vector_paths_for
from methodology_extractor import _normalize_technique_id
from mistral_extractor import MistralExtractor, MistralGenerationError
from pdf_extractor import chunk_text, extract_text_from_pdf
from review_cases import NONE_LABEL, _flag, read_review

MODES = ("names", "definitions")


def gold_labels(review_rows: list[dict]) -> dict:
    """record_id -> technique correcte (None = aucune), pour les cas gardés à la relecture."""
    gold = {}
    for r in review_rows:
        if not _flag(r["garder"]):
            continue
        if _flag(r["categorie_ok"]):
            gold[r["record_id"]] = None if r["categorie"] == "non validée" else r["categorie"]
        else:
            good = r["bonne_categorie"].strip()
            gold[r["record_id"]] = None if good.lower() == NONE_LABEL else good
    return gold


def find_pdf(name: str, pdf_dirs: list[str]) -> str | None:
    for d in pdf_dirs:
        hits = glob.glob(os.path.join(d, "**", name), recursive=True)
        if hits:
            return hits[0]
    return None


def chunk_contexts(table: list[dict], pdf_dirs: list[str], methodology_dir: str) -> dict:
    """record_id -> texte de l'extrait d'origine (absent si introuvable)."""
    contexts = {}
    for paper in sorted({r["source_paper"] for r in table}):
        log = os.path.join(methodology_dir, f"methodology_{os.path.splitext(paper)[0]}.jsonl")
        pdf = find_pdf(paper, pdf_dirs)
        if not os.path.exists(log) or pdf is None:
            print(f"[⚠] {paper} : {'journal Layer 2' if not os.path.exists(log) else 'PDF'} introuvable "
                  "— classification sur le résumé seul")
            continue
        index_by_summary = {m.get("attack_summary"): m["chunk_index"] for m in read_jsonl(log)
                            if m.get("attack_summary") and "chunk_index" in m}
        chunks = [c for _, c in chunk_text(extract_text_from_pdf(pdf, verbose=False))]
        for r in table:
            i = index_by_summary.get(r["attack_summary"]) if r["source_paper"] == paper else None
            if i is not None and i < len(chunks):
                contexts[r["record_id"]] = chunks[i]
    return contexts


def classify(mistral: MistralExtractor, record: dict, context: str | None, mode: str,
             domain: str, techniques: dict) -> tuple[str | None, str]:
    labels = attack_taxonomy.shortlist_labels_block(domain, techniques, with_descriptions=(mode == "definitions"))
    prompt = classify_prompt(domain, labels, record["attack_summary"], context or record["attack_summary"],
                             disambiguation=(mode == "definitions"))
    try:
        raw = mistral._generate(prompt)
    except MistralGenerationError as e:
        return None, f"<échec génération : {e}>"
    proposed = _normalize_technique_id(mistral._parse_json_full(raw).get("mitre_technique_id"), domain)
    return (proposed if attack_taxonomy.is_in_shortlist(proposed, domain) else None), raw


def scores(pred: dict, gold: dict) -> dict:
    ids = [i for i in gold if i in pred]
    validated = [i for i in ids if pred[i]]
    correct_validated = sum(pred[i] == gold[i] for i in validated)
    correct_all = sum(pred[i] == gold[i] for i in ids)
    errors = Counter((pred[i] or "null", gold[i] or "aucune") for i in ids if pred[i] != gold[i])
    return {"n": len(ids), "n_validated": len(validated),
            "accuracy_validated": [correct_validated, len(validated)],
            "accuracy_validated_wilson": wilson(correct_validated, len(validated)),
            "accuracy_all": [correct_all, len(ids)], "accuracy_all_wilson": wilson(correct_all, len(ids)),
            "confusions": [{"predicted": p, "correct": g, "count": c} for (p, g), c in errors.most_common()]}


def main():
    parser = argparse.ArgumentParser(description="Reclassification ATLAS des cas existants, avant/après prompt.")
    parser.add_argument("--table", required=True, help="table BRUTE (sortie du pipeline)")
    parser.add_argument("--review", required=True, help="CSV de relecture (review_cases.py)")
    parser.add_argument("--pdf-dir", nargs="+", default=["files"])
    parser.add_argument("--methodology-dir", default="results")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--backend", default="ollama", choices=["ollama", "transformers"])
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--output-dir", default="results/reclassification")
    parser.add_argument("--write-table", action="store_true",
                        help="écrire <table>_reclassified.jsonl avec les techniques du mode definitions")
    args = parser.parse_args()

    table = load_table(args.table)
    if any("review" in r for r in table):
        raise SystemExit(f"[✗] {args.table} est une table corrigée : passer la table brute (_raw).")
    _, review_rows = read_review(args.review)
    gold = gold_labels(review_rows)
    missing = [i for i in gold if i not in {r["record_id"] for r in table}]
    if missing:
        raise SystemExit(f"[✗] {len(missing)} cas relus absents de {args.table} : mauvaise table ?")
    techniques = attack_taxonomy.load_techniques(args.domain)
    contexts = chunk_contexts(table, args.pdf_dir, args.methodology_dir)
    print(f"{len(table)} cas ({len(gold)} relus) ; extrait d'origine retrouvé pour {len(contexts)}")

    os.makedirs(args.output_dir, exist_ok=True)
    mistral = MistralExtractor(backend=args.backend)
    results = {"layer2_original": scores({r["record_id"]: r.get("category") for r in table}, gold)}
    predictions = {}
    for mode in args.modes:
        # Reprise : un run interrompu reprend là où il s'est arrêté.
        path = os.path.join(args.output_dir, f"predictions_{mode}.jsonl")
        done = {p["record_id"]: p["predicted"] for p in read_jsonl(path)} if os.path.exists(path) else {}
        for k, r in enumerate(table, 1):
            if r["record_id"] in done:
                continue
            print(f"  [{mode}] {k}/{len(table)} ...", end=" ", flush=True)
            pred, raw = classify(mistral, r, contexts.get(r["record_id"]), mode, args.domain, techniques)
            print(pred)
            done[r["record_id"]] = pred
            append_jsonl(path, {"record_id": r["record_id"], "predicted": pred, "gold": gold.get(r["record_id"], "non relu"),
                                "layer2_original": r.get("category"),
                                "context": "chunk" if r["record_id"] in contexts else "summary",
                                "raw_model_output": raw})
        predictions[mode] = done
        results[mode] = scores(done, gold)

    print(f"\n{'configuration':18} {'justesse (identifiants validés)':>34} {'justesse (tous les cas)':>26}")
    for name, s in results.items():
        k, n = s["accuracy_validated"]
        lo, hi = s["accuracy_validated_wilson"]
        ka, na = s["accuracy_all"]
        print(f"{name:18} {k:>4}/{n:<4} = {k / max(n, 1):6.1%} [{lo:.0%}–{hi:.0%}] {ka:>8}/{na:<4} = {ka / max(na, 1):6.1%}")
        for c in s["confusions"][:4]:
            print(f"{'':20}{c['count']:3}×  {c['predicted']} -> {c['correct']}")
    print("\n[!] La règle de distinction a été écrite après l'analyse des erreurs sur ces cas : gain optimiste.")

    out = os.path.join(args.output_dir, f"reclassification_{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"table": args.table, "review": args.review, "n_cases": len(table), "n_reviewed": len(gold),
                   "n_with_chunk": len(contexts), "results": results}, f, indent=2, ensure_ascii=False)
    print(f"[✓] {out}")

    if args.write_table and "definitions" in predictions:
        stem = os.path.splitext(args.table)[0] + "_reclassified"
        for r in table:
            r["category_layer2"] = r.get("category")
            r["category"] = predictions["definitions"][r["record_id"]]
            r["category_name"] = attack_taxonomy.technique_name(r["category"], techniques, args.domain)
        write_jsonl(stem + ".jsonl", table)
        for src, dst in zip(vector_paths_for(args.table), vector_paths_for(stem + ".jsonl")):
            if os.path.exists(src):
                shutil.copy2(src, dst)
        print(f"[✓] {stem}.jsonl (+ .npz) : techniques du mode definitions, category_layer2 conservé")


if __name__ == "__main__":
    main()
