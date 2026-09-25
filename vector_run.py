"""
verifier_run.py
-----------------
Contrôle qualité d'un run de build_knowledge.py, à lancer APRÈS lui, sans
Ollama ni GLiNER (lit uniquement les fichiers produits).

Ne remplace PAS la relecture à la main des résumés — il la CIBLE : plutôt que
de relire les 60 enregistrements d'un corpus, on relit d'abord ceux que ce
script signale. Chaque statistique correspond à un mode d'échec déjà rencontré
en conditions réelles sur le corpus supply chain :

  - taux de catégories validées trop bas -> le prompt de Layer 2 et la
    short-list du domaine ne parlent pas de la même chose (c'est ce qui avait
    fait chuter la précision à 0.1159 avant le fix de la taxonomie) ;
  - 100% de cas "generic" -> les labels identifiants de specificity.py ne
    correspondent à aucun label de la taxonomie réellement utilisée : le
    filtre est un no-op silencieux, pas un résultat ;
  - toutes les mitigations à 1.0 de généralisabilité -> même problème côté
    generalizability.py ;
  - un seul mitigation_type jamais proposé -> le prompt décrit mal ce type ;
  - texte de remplissage résiduel ("not explicitly mentioned") -> un variant
    que is_filler_text ne connaît pas encore.

Usage :
    python verifier_run.py
    python verifier_run.py --table results/knowledge_table.jsonl
    python verifier_run.py --paper greshake.pdf
"""

import argparse
from collections import Counter

from config import KNOWLEDGE_TABLE_PATH, MITIGATION_TYPES
from jsonl_utils import read_jsonl
from mistral_extractor import is_filler_text

# Un résumé plus long que ça n'est plus un résumé : le prompt demande 1-2
# phrases, au-delà le modèle recopie un paragraphe du papier.
MAX_SUMMARY_WORDS = 80


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.0f}%" if total else "n/a"


def _section(title: str) -> None:
    print(f"\n{'-' * 62}\n{title}\n{'-' * 62}")


def verifier(table_path: str, paper: str = None) -> int:
    records = read_jsonl(table_path)
    if paper:
        records = [r for r in records if r.get("source_paper") == paper]
    if not records:
        print(
            f"[!] Aucun enregistrement dans {table_path}"
            + (f" pour {paper!r}" if paper else "")
            + ".\n    Le run de build_knowledge.py a-t-il bien abouti ?"
        )
        return 1

    total = len(records)
    alertes = []

    _section(f"TABLE : {table_path}  ({total} enregistrement(s))")
    par_paper = Counter(r.get("source_paper") for r in records)
    for nom, n in par_paper.most_common():
        print(f"  {n:4}  {nom}")
    par_domaine = Counter(r.get("domain") for r in records)
    print(f"\n  domaine(s) : {dict(par_domaine)}")

    # --- Catégories MITRE -------------------------------------------------
    _section("CATÉGORIES MITRE (le modèle propose, le code valide)")
    validees = [r for r in records if r.get("category")]
    print(f"  validées : {len(validees)}/{total} ({_pct(len(validees), total)})")
    for cat, n in Counter(
        f"{r['category']} — {r.get('category_name')}" for r in validees
    ).most_common():
        print(f"    {n:3}  {cat}")
    if len(validees) / total < 0.3:
        alertes.append(
            f"Seulement {_pct(len(validees), total)} de catégories validées. "
            "Vérifier que la short-list du domaine couvre bien les attaques "
            "de ce papier (attack_taxonomy.LLM_THREAT_TECHNIQUE_IDS)."
        )
    if len(validees) and len(set(r["category"] for r in validees)) == 1:
        alertes.append(
            "Toutes les catégories validées sont identiques — le modèle "
            "choisit peut-être la première de la liste par défaut plutôt que "
            "d'analyser le texte."
        )

    # --- Concret vs générique --------------------------------------------
    _section("SPÉCIFICITÉ (cas concret vs reformulation du sujet)")
    concrets = [r for r in records if r.get("specificity") == "concrete"]
    print(f"  concrets  : {len(concrets)}/{total} ({_pct(len(concrets), total)})")
    print(f"  génériques: {total - len(concrets)}/{total}")
    if not concrets:
        alertes.append(
            "AUCUN cas concret. Soit le papier est purement théorique (normal "
            "pour Wolf et al.), soit les labels de specificity.py ne "
            "correspondent pas à la taxonomie du domaine — dans ce cas le "
            "filtre ne marque jamais rien et le résultat est faux, pas vide."
        )

    # --- Mitigations ------------------------------------------------------
    _section("MITIGATIONS (structurées : type + résumé)")
    avec_mitigation = [r for r in records if r.get("mitigation_summary")]
    print(
        f"  avec mitigation : {len(avec_mitigation)}/{total} "
        f"({_pct(len(avec_mitigation), total)})"
    )
    types_vus = Counter(r.get("mitigation_type") for r in avec_mitigation)
    for type_name in MITIGATION_TYPES:
        print(f"    {types_vus.get(type_name, 0):3}  {type_name}")
    non_types = types_vus.get(None, 0)
    if non_types:
        print(f"    {non_types:3}  (type non validé — résumé conservé)")
    if avec_mitigation and non_types == len(avec_mitigation):
        alertes.append(
            "AUCUNE mitigation n'a reçu un type valide : le modèle ignore la "
            "consigne de typage, ou les trois types ne correspondent pas aux "
            "défenses décrites dans ce papier."
        )

    scores = [
        r["generalizability_score"]
        for r in records
        if r.get("generalizability_score") is not None
    ]
    if scores:
        print(
            f"\n  généralisabilité : min={min(scores)} max={max(scores)} "
            f"moyenne={sum(scores) / len(scores):.3f}"
        )
        if len(set(scores)) == 1:
            alertes.append(
                f"Toutes les mitigations ont le même score ({scores[0]}) — les "
                "labels de generalizability.py ne matchent probablement aucune "
                "entité de la taxonomie du domaine (no-op silencieux)."
            )

    # --- Contrôles de contenu --------------------------------------------
    _section("CONTRÔLES DE CONTENU")
    fillers = [
        r
        for r in records
        for champ in ("attack_summary", "mitigation_summary")
        if r.get(champ) and is_filler_text(r[champ])
    ]
    trop_longs = [
        r
        for r in records
        if r.get("attack_summary") and len(r["attack_summary"].split()) > MAX_SUMMARY_WORDS
    ]
    print(f"  texte de remplissage résiduel : {len(fillers)}")
    print(f"  résumés > {MAX_SUMMARY_WORDS} mots      : {len(trop_longs)}")
    if fillers:
        alertes.append(
            f"{len(fillers)} champ(s) de remplissage ont échappé au filtre — "
            "ajouter le variant rencontré dans mistral_extractor._FILLER_*_RE."
        )
    for r in trop_longs[:3]:
        print(f"    [{len(r['attack_summary'].split())} mots] {r['attack_summary'][:110]}...")

    # --- À relire en priorité --------------------------------------------
    _section("À RELIRE EN PRIORITÉ (cas concrets avec mitigation typée)")
    a_relire = [
        r
        for r in records
        if r.get("specificity") == "concrete" and r.get("mitigation_type")
    ]
    if not a_relire:
        print("  (aucun — relire alors les cas concrets sans mitigation)")
        a_relire = concrets[:5]
    for r in a_relire[:8]:
        print(f"\n  [{r.get('category') or 'catégorie non validée'}] {r['attack_summary']}")
        if r.get("mitigation_summary"):
            print(f"    -> [{r.get('mitigation_type')}] {r['mitigation_summary']}")

    # --- Verdict ----------------------------------------------------------
    _section("ALERTES")
    if not alertes:
        print("  Aucune. Les indicateurs sont cohérents — reste la relecture")
        print("  à la main des résumés ci-dessus, que rien ne remplace.")
        return 0
    for a in alertes:
        print(f"  [!] {a}")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Contrôle qualité d'un run de build_knowledge.py (hors ligne)."
    )
    parser.add_argument("--table", default=KNOWLEDGE_TABLE_PATH)
    parser.add_argument(
        "--paper",
        default=None,
        help="Ne vérifier qu'un seul paper (valeur du champ source_paper, "
        "ex: greshake_indirect_injection.pdf).",
    )
    args = parser.parse_args()
    raise SystemExit(verifier(args.table, args.paper))


if __name__ == "__main__":
    main()
