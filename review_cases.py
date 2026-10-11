"""
review_cases.py
-----------------
Relecture manuelle de la knowledge table, en trois étapes. Elle sert à deux
choses à la fois :

  (a) MESURER la justesse de la Layer 2 pour le papier (§ "MITRE ATLAS
      Classification Accuracy") : parmi les cas dont l'identifiant ATLAS a
      passé la validation, combien portent la BONNE technique ? Combien de
      mitigations extraites sont de vraies mitigations ? Ces chiffres sont
      calculés sur la sortie BRUTE du pipeline, avant toute correction ;
  (b) construire une table CURÉE, qui ne sert que de BORNE SUPÉRIEURE : ce
      que donnerait le système si la classification était parfaite. Les
      expériences (calibration, Table IV) tournent sur la table BRUTE, sortie
      réelle du pipeline : corriger à la main la table utilisée ferait perdre
      le caractère automatique de la construction, qui distingue ce travail
      des bases curées à la main (LVD/ATAG).

1. export — un CSV (Excel, séparateur ;) avec un cas par ligne :
       python review_cases.py export --table results/knowledge_table_llm.jsonl
   Colonnes à remplir :
       categorie_ok    o = la technique proposée est la bonne
                       n = mauvaise technique (ou "non validée" alors qu'une technique convient)
                       (pour un cas "non validée" sans technique adaptée : o)
       bonne_categorie si categorie_ok = n : l'ID ATLAS correct de la short-list
                       (liste dans le fichier _shortlist.txt) ou "aucune"
       mitigation_ok   o = vraie mitigation de l'attaque ; n = pas une mitigation
                       (résultat expérimental, description de l'attaque...) ;
                       vide si la mitigation est nulle
       garder          o (pré-rempli) ; n = pas un cas d'attaque exploitable
                       (exemple de requête nuisible, phrase sans attaque...)
       remarque        libre

2. score — justesse de classification et validité des mitigations, avec
   intervalles de Wilson à 95 %, et phrase LaTeX pour le papier :
       python review_cases.py score --review results/review_knowledge_table_llm.csv

3. apply — écrit la table corrigée (catégories corrigées, mitigations
   invalides mises à null, cas "garder = n" retirés du JSONL ET des deux
   stores vectoriels), après une copie de sauvegarde *.before_review :
       python review_cases.py apply --review results/review_knowledge_table_llm.csv
   Les embeddings d'attaque ne changent pas (le résumé d'attaque n'est pas
   modifié) : aucun appel à Ollama n'est nécessaire.

Faire 2 AVANT 3 : le score doit porter sur la sortie brute du pipeline.

4. split — après apply, sépare les deux versions en deux tables nommées,
   chacune avec ses deux stores vectoriels :
       python review_cases.py split --table results/knowledge_table_llm.jsonl
   -> knowledge_table_llm_raw.jsonl     (sortie du pipeline, avant relecture)
   -> knowledge_table_llm_curated.jsonl (après relecture, borne supérieure)

5. iaa-export / iaa-score — accord inter-annotateurs : tire N cas au hasard
   (graine fixe) dans un CSV VIERGE pour une seconde personne, qui le remplit
   sans voir la première relecture, puis calcule le kappa de Cohen sur la
   technique correcte, la validité de la mitigation et la décision de garder :
       python review_cases.py iaa-export --review results/review_knowledge_table_llm.csv
       python review_cases.py iaa-score --review results/review_knowledge_table_llm.csv \
           --second results/review_knowledge_table_llm_iaa.csv
"""

import argparse
import csv
import json
import os
import random
import shutil
import time
from collections import Counter

import attack_taxonomy
from audit_false_positives import read_csv_rows, wilson
from config import DEFAULT_DOMAIN
from jsonl_utils import write_jsonl
from knowledge_table import load_table, vector_paths_for
from vector_store import remove_vectors

FIELDS = ["n", "record_id", "paper", "categorie", "nom_categorie", "resume_attaque", "mitigation",
          "type_mitigation", "categorie_ok", "bonne_categorie", "mitigation_ok", "garder", "remarque"]
YES = {"o", "oui", "y", "yes", "1"}
NO = {"n", "non", "no", "0"}
NONE_LABEL = "aucune"


def _flag(value: str):
    v = (value or "").strip().lower()
    return True if v in YES else False if v in NO else None


def default_review_path(table_path: str) -> str:
    base = os.path.splitext(os.path.basename(table_path))[0]
    return os.path.join(os.path.dirname(table_path) or ".", f"review_{base}.csv")


def read_review(path: str) -> tuple[dict, list[dict]]:
    with open(os.path.splitext(path)[0] + "_meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    rows = read_csv_rows(path)
    required = {"n", "record_id", "categorie", "mitigation", "categorie_ok", "bonne_categorie", "mitigation_ok", "garder"}
    missing = required - set(rows[0] if rows else ())
    if missing:
        raise SystemExit(f"[✗] Colonnes introuvables dans {path} : {', '.join(sorted(missing))}.\n"
                         f"    Colonnes lues : {', '.join(rows[0]) if rows else '(fichier vide)'}\n"
                         "    Réenregistrer le fichier depuis Excel au format « CSV UTF-8 ».")
    return meta, rows


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


def _technique(row: dict) -> str:
    """Technique jugée correcte par l'annotateur sur une ligne ("aucune" si aucune)."""
    if _flag(row["categorie_ok"]):
        return NONE_LABEL if row["categorie"] == "non validée" else row["categorie"]
    good = (row.get("bonne_categorie") or "").strip()
    return NONE_LABEL if not good or good.lower() == NONE_LABEL else good


def cohen_kappa(a: list, b: list) -> float:
    """Kappa de Cohen entre deux listes d'étiquettes de même longueur."""
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def check_rows(rows: list[dict], domain: str) -> list[str]:
    """Liste des problèmes de saisie ; vide si le CSV est complet et cohérent."""
    problems = []
    for r in rows:
        n = r["n"]
        ok = _flag(r["categorie_ok"])
        if ok is None:
            problems.append(f"ligne {n} : categorie_ok doit valoir o ou n")
        good = (r.get("bonne_categorie") or "").strip()
        if ok is False and not good:
            problems.append(f"ligne {n} : categorie_ok = n mais bonne_categorie vide")
        if ok is False and good and good.lower() != NONE_LABEL and not attack_taxonomy.is_in_shortlist(good, domain):
            problems.append(f"ligne {n} : bonne_categorie {good!r} absente de la short-list ATLAS")
        if r["mitigation"] and _flag(r["mitigation_ok"]) is None:
            problems.append(f"ligne {n} : mitigation présente, mitigation_ok doit valoir o ou n")
        if _flag(r["garder"]) is None:
            problems.append(f"ligne {n} : garder doit valoir o ou n")
    return problems


def cmd_export(args):
    table = load_table(args.table)
    if not table:
        raise SystemExit(f"[✗] Table vide ou absente : {args.table}")
    out = args.output or default_review_path(args.table)
    if os.path.exists(out) and not args.force:
        raise SystemExit(f"[✗] {out} existe déjà (relecture en cours ?) — --force pour l'écraser.")
    techniques = attack_taxonomy.load_techniques(args.domain)

    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        w.writeheader()
        for i, r in enumerate(sorted(table, key=lambda r: (r.get("source_paper") or "", r.get("category") or "")), 1):
            w.writerow({
                "n": i, "record_id": r["record_id"], "paper": r.get("source_paper"),
                "categorie": r.get("category") or "non validée", "nom_categorie": r.get("category_name") or "",
                "resume_attaque": r.get("attack_summary") or "", "mitigation": r.get("mitigation_summary") or "",
                "type_mitigation": r.get("mitigation_type") or "",
                "categorie_ok": "", "bonne_categorie": "", "mitigation_ok": "", "garder": "o", "remarque": "",
            })
    with open(os.path.splitext(out)[0] + "_shortlist.txt", "w", encoding="utf-8") as f:
        f.write("Techniques ATLAS acceptées dans bonne_categorie (short-list du domaine), ou \"aucune\" :\n\n")
        f.write(attack_taxonomy.shortlist_labels_block(args.domain, techniques) + "\n")
    meta = {"table": args.table, "domain": args.domain, "n_cases": len(table),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.splitext(out)[0] + "_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"[✓] {len(table)} cas -> {out}")
    print(f"    techniques acceptées : {os.path.splitext(out)[0]}_shortlist.txt")
    print(f"    Remplir categorie_ok / bonne_categorie / mitigation_ok / garder, puis : "
          f"python review_cases.py score --review {out}")


def _rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} [IC 95 % : {lo:.1%} – {hi:.1%}]" if n else "—"


def cmd_score(args):
    meta, rows = read_review(args.review)
    problems = check_rows(rows, meta["domain"])
    if problems:
        raise SystemExit("[✗] CSV incomplet :\n    " + "\n    ".join(problems))

    kept = [r for r in rows if _flag(r["garder"])]
    validated = [r for r in kept if r["categorie"] != "non validée"]
    unvalidated = [r for r in kept if r["categorie"] == "non validée"]
    correct = [r for r in validated if _flag(r["categorie_ok"])]
    abstain_ok = [r for r in unvalidated if _flag(r["categorie_ok"])]
    with_mit = [r for r in kept if r["mitigation"]]
    mit_ok = [r for r in with_mit if _flag(r["mitigation_ok"])]
    errors = Counter((r["categorie"], r["bonne_categorie"].strip()) for r in validated if not _flag(r["categorie_ok"]))

    print(f"Relecture de {len(rows)} cas ({meta['table']}) — {len(rows) - len(kept)} retiré(s) (garder = n)")
    print(f"  justesse de la technique ATLAS (cas validés)   : {_rate(len(correct), len(validated))}")
    print(f"  abstentions justifiées (cas non validés)        : {_rate(len(abstain_ok), len(unvalidated))}")
    print(f"  mitigations valides (mitigations non nulles)    : {_rate(len(mit_ok), len(with_mit))}")
    if errors:
        print("  confusions les plus fréquentes (proposée -> correcte) :")
        for (prop, good), c in errors.most_common(8):
            print(f"    {c:3}×  {prop} -> {good}")
    per_paper = {}
    for r in validated:
        p = per_paper.setdefault(r["paper"], [0, 0])
        p[0] += bool(_flag(r["categorie_ok"]))
        p[1] += 1
    print("  par paper (justesse ATLAS) :")
    for paper, (k, n) in sorted(per_paper.items()):
        print(f"    {k:3}/{n:<3} {paper}")

    lo, hi = wilson(len(correct), len(validated))
    mlo, mhi = wilson(len(mit_ok), len(with_mit))
    sentence = (f"A manual review of all {len(validated)} retained cases with a validated identifier found "
                f"{len(correct)} ({len(correct) / len(validated):.1%}; 95% Wilson interval {lo:.1%}--{hi:.1%}) "
                f"to carry the correct ATLAS technique, and {len(mit_ok)} of the {len(with_mit)} non-null mitigation "
                f"summaries ({len(mit_ok) / len(with_mit):.1%}; {mlo:.1%}--{mhi:.1%}) to describe an actual "
                f"countermeasure to the extracted attack.").replace("%", r"\%")
    out = os.path.splitext(args.review)[0] + "_score.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({**meta, "review": args.review, "n_reviewed": len(rows), "n_removed": len(rows) - len(kept),
                   "category_accuracy": [len(correct), len(validated)], "category_accuracy_wilson": [lo, hi],
                   "abstention_correct": [len(abstain_ok), len(unvalidated)],
                   "mitigation_valid": [len(mit_ok), len(with_mit)], "mitigation_valid_wilson": [mlo, mhi],
                   "confusions": [{"proposed": p, "correct": g, "count": c} for (p, g), c in errors.most_common()],
                   "per_paper": per_paper, "latex_sentence": sentence}, f, indent=2, ensure_ascii=False)
    print(f"\nPhrase pour le papier :\n{sentence}\n\n[✓] {out}")


def cmd_apply(args):
    meta, rows = read_review(args.review)
    domain = meta["domain"]
    techniques = attack_taxonomy.load_techniques(domain)
    problems = check_rows(rows, domain)
    if problems:
        raise SystemExit("[✗] CSV incomplet :\n    " + "\n    ".join(problems))
    table_path = meta["table"]
    table = load_table(table_path)
    if any("review" in r for r in table) and not args.force:
        raise SystemExit("[✗] Cette table a déjà été corrigée (champ 'review'). --force pour réappliquer.")
    by_id = {r["record_id"]: r for r in rows}
    missing = [r["record_id"] for r in table if r["record_id"] not in by_id]
    if missing:
        raise SystemExit(f"[✗] {len(missing)} cas de la table absents du CSV : la table a changé depuis l'export.")

    attack_npz, mitigation_npz = vector_paths_for(table_path)
    for path in (table_path, attack_npz, mitigation_npz):
        if os.path.exists(path):
            shutil.copy2(path, path + ".before_review")

    kept, removed, null_mitigation, recategorized = [], [], [], 0
    for rec in table:
        rv = by_id[rec["record_id"]]
        if not _flag(rv["garder"]):
            removed.append(rec["record_id"])
            continue
        review = {"category_original": rec.get("category"), "mitigation_removed": False}
        if not _flag(rv["categorie_ok"]):
            good = rv["bonne_categorie"].strip()
            rec["category"] = None if good.lower() == NONE_LABEL else good
            rec["category_name"] = attack_taxonomy.technique_name(rec["category"], techniques, domain) if rec["category"] else None
            recategorized += 1
        if rec.get("mitigation_summary") and not _flag(rv["mitigation_ok"]):
            rec["mitigation_summary"] = rec["mitigation_type"] = rec["generalizability_score"] = None
            review["mitigation_removed"] = True
            null_mitigation.append(rec["record_id"])
        if rv.get("remarque"):
            review["note"] = rv["remarque"]
        rec["review"] = review
        kept.append(rec)

    write_jsonl(table_path, kept)
    remove_vectors(attack_npz, removed)
    remove_vectors(mitigation_npz, removed + null_mitigation)
    print(f"[✓] {table_path} : {len(kept)} cas gardés, {len(removed)} retirés, {recategorized} recatégorisés, "
          f"{len(null_mitigation)} mitigation(s) mise(s) à null")
    print(f"    sauvegarde de l'état précédent : {table_path}.before_review (+ .npz)")
    cats = Counter(r.get("category") or "non validée" for r in kept)
    for c, n in cats.most_common():
        print(f"    {n:4}  {c}")


def cmd_split(args):
    table_path = args.table
    stem = os.path.splitext(table_path)[0]
    src_npz = vector_paths_for(table_path)
    backup = [table_path + ".before_review"] + [p + ".before_review" for p in src_npz]
    missing = [p for p in backup if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"[✗] Sauvegarde absente : {', '.join(missing)} — lancer apply d'abord.")
    if not any("review" in r for r in load_table(table_path)):
        raise SystemExit(f"[✗] {table_path} n'est pas la table corrigée (aucun champ 'review').")

    for variant, sources in (("raw", backup), ("curated", [table_path, *src_npz])):
        target = f"{stem}_{variant}.jsonl"
        if os.path.exists(target) and not args.force:
            raise SystemExit(f"[✗] {target} existe déjà — --force pour l'écraser.")
        for src, dst in zip(sources, [target, *vector_paths_for(target)]):
            shutil.copy2(src, dst)
        table = load_table(target)
        cats = Counter(r.get("category") or "non validée" for r in table)
        print(f"[✓] {target} : {len(table)} cas, {len(cats)} technique(s)")
    print("    Expériences (calibration, Table IV) : table _raw ; borne supérieure : table _curated.")


def cmd_iaa_export(args):
    _, rows = read_review(args.review)
    sample = random.Random(args.seed).sample(rows, min(args.n, len(rows)))
    out = args.output or os.path.splitext(args.review)[0] + "_iaa.csv"
    if os.path.exists(out) and not args.force:
        raise SystemExit(f"[✗] {out} existe déjà — --force pour l'écraser.")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(sorted(sample, key=lambda r: int(r["n"])), 1):
            w.writerow({**{k: r.get(k, "") for k in FIELDS}, "n": i,
                        "categorie_ok": "", "bonne_categorie": "", "mitigation_ok": "", "garder": "", "remarque": ""})
    shutil.copy2(os.path.splitext(args.review)[0] + "_meta.json", os.path.splitext(out)[0] + "_meta.json")
    print(f"[✓] {len(sample)} cas tirés au hasard (graine {args.seed}) -> {out}")
    print("    À remplir par une seconde personne, SANS voir la première relecture "
          "(mêmes consignes ; garder = o / n).")


def cmd_iaa_score(args):
    _, first = read_review(args.review)
    meta, second = read_review(args.second)
    problems = check_rows(second, meta["domain"])
    if problems:
        raise SystemExit("[✗] Seconde annotation incomplète :\n    " + "\n    ".join(problems))
    by_id = {r["record_id"]: r for r in first}
    pairs = [(by_id[r["record_id"]], r) for r in second if r["record_id"] in by_id]
    both_kept = [(a, b) for a, b in pairs if _flag(a["garder"]) and _flag(b["garder"])]
    with_mit = [(a, b) for a, b in both_kept if a["mitigation"]]
    results = {}
    for name, items, key in (
        ("garder", pairs, lambda r: _flag(r["garder"])),
        ("technique", both_kept, _technique),
        ("mitigation_ok", with_mit, lambda r: _flag(r["mitigation_ok"])),
    ):
        a, b = [key(x) for x, _ in items], [key(y) for _, y in items]
        agree = sum(x == y for x, y in zip(a, b))
        results[name] = {"n": len(items), "agreement": agree, "kappa": round(cohen_kappa(a, b), 3)}
        print(f"  {name:14} n={len(items):3}  accord {agree}/{len(items)}"
              f" = {agree / max(len(items), 1):.0%}   kappa de Cohen = {results[name]['kappa']:.2f}")
    out = os.path.splitext(args.second)[0] + "_score.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"first": args.review, "second": args.second, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"[✓] {out}")


def main():
    parser = argparse.ArgumentParser(description="Relecture manuelle de la knowledge table.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="écrit le CSV de relecture")
    e.add_argument("--table", required=True)
    e.add_argument("--domain", default=DEFAULT_DOMAIN)
    e.add_argument("--output", default=None)
    e.add_argument("--force", action="store_true")
    e.set_defaults(func=cmd_export)
    s = sub.add_parser("score", help="justesse ATLAS et validité des mitigations (sortie brute)")
    s.add_argument("--review", required=True)
    s.set_defaults(func=cmd_score)
    a = sub.add_parser("apply", help="écrit la table corrigée (sauvegarde *.before_review)")
    a.add_argument("--review", required=True)
    a.add_argument("--force", action="store_true")
    a.set_defaults(func=cmd_apply)
    sp = sub.add_parser("split", help="sépare table brute (_raw) et table curée (_curated)")
    sp.add_argument("--table", required=True)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_split)
    ie = sub.add_parser("iaa-export", help="CSV vierge de N cas pour une seconde annotation")
    ie.add_argument("--review", required=True)
    ie.add_argument("--n", type=int, default=25)
    ie.add_argument("--seed", type=int, default=7)
    ie.add_argument("--output", default=None)
    ie.add_argument("--force", action="store_true")
    ie.set_defaults(func=cmd_iaa_export)
    isc = sub.add_parser("iaa-score", help="kappa de Cohen entre les deux annotations")
    isc.add_argument("--review", required=True)
    isc.add_argument("--second", required=True)
    isc.set_defaults(func=cmd_iaa_score)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
