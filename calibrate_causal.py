"""
calibrate_causal.py
--------------------
Calibre les deux seuils du vérificateur causal (causal.py) sur des données de
DÉVELOPPEMENT, distinctes des 18 requêtes de la Table IV.

Pourquoi : le seuil sémantique a priori (0,70) rejetait toutes les mesures
adaptées du premier run (cosinus observés 0,46-0,67). Le baisser en regardant
ces résultats serait un réglage sur le test. On le fixe donc sur une autre
source : la base de cas elle-même.

Données de développement : des paires (cas source i, cas cible j) de la même
technique (de préférence d'articles différents). On demande à Mistral
d'adapter la mitigation de i à l'attaque de j, avec le prompt de Propose
(PROMPT_ADAPT) et la chaîne causale de j. Pour chaque mesure produite :
  positif sémantique  cosinus(mesure, mitigation de i)    — ce qu'elle adapte
  négatif sémantique  cosinus(mesure, mitigation de k)    — k : cas tiré au
                      hasard dans une AUTRE technique
  positif maillon     cosinus(mesure, maillon de j qu'elle dit casser)
  négatif maillon     cosinus(mesure, même maillon de la chaîne de k)
Chaque seuil est celui qui maximise l'indice de Youden (TPR + TNR - 1) ; un
bootstrap donne son intervalle. Les requêtes de test ne sont jamais lues.

Table par défaut : la table curée, dont les techniques sont celles de la
relecture (des paires « même technique » fondées sur des labels faux
fausseraient les positifs). Les cas sont la base de connaissance, pas des
requêtes de test.

Reprise : chaque paire traitée est ajoutée à --cache ; une relance reprend
là où le run s'est arrêté (Mistral sur CPU est lent).

Usage :
    python calibrate_causal.py
    python calibrate_causal.py --table results/knowledge_table_llm_curated.jsonl --n 20
    python run_remediation.py ... --calibration results/causal_calibration.json
"""

import argparse
import json
import os
import random
import statistics

from causal import LINKS, _cosine, normalize_link
from jsonl_utils import append_jsonl, read_jsonl
from knowledge_table import load_table
from remediation import Remediator
from run_remediation import file_sha256

DEFAULT_TABLE = "results/knowledge_table_llm_curated.jsonl"


def build_pairs(table: list[dict], n: int, seed: int) -> list[tuple[dict, dict, dict]]:
    """(source i, cible j même technique, négatif k autre technique), tirés avec une graine fixe."""
    rng = random.Random(seed)
    cases = [c for c in table if c.get("mitigation_summary") and c.get("category") and c.get("attack_summary")]
    by_cat = {}
    for c in cases:
        by_cat.setdefault(c["category"], []).append(c)
    pairs = []
    for i in cases:
        same = [j for j in by_cat[i["category"]] if j["record_id"] != i["record_id"]]
        other_paper = [j for j in same if j.get("source_paper") != i.get("source_paper")]
        for j in other_paper or same:
            pairs.append((i, j))
    rng.shuffle(pairs)
    # Au plus une paire par cas source, pour ne pas sur-représenter une mitigation
    chosen, used = [], set()
    for i, j in pairs:
        if i["record_id"] in used:
            continue
        others = [k for k in cases if k["category"] != i["category"]]
        if not others:
            continue
        used.add(i["record_id"])
        chosen.append((i, j, rng.choice(others)))
        if len(chosen) == n:
            break
    return chosen


def youden(pos: list[float], neg: list[float]) -> dict:
    """Seuil maximisant TPR + TNR - 1 (à égalité, le plus bas : le moins strict)."""
    best = None
    for t in sorted(set(pos) | set(neg)):
        tpr = sum(p >= t for p in pos) / len(pos)
        tnr = sum(x < t for x in neg) / len(neg)
        if best is None or tpr + tnr - 1 > best["j"] + 1e-12:
            best = {"threshold": round(t, 3), "j": tpr + tnr - 1, "tpr": round(tpr, 3), "tnr": round(tnr, 3)}
    best["balanced_accuracy"] = round((best["tpr"] + best["tnr"]) / 2, 3)
    best["j"] = round(best["j"], 3)
    return best


def bootstrap(pos: list[float], neg: list[float], n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    ts = []
    for _ in range(n_boot):
        p = [rng.choice(pos) for _ in pos]
        q = [rng.choice(neg) for _ in neg]
        ts.append(youden(p, q)["threshold"])
    ts.sort()
    return round(ts[int(0.025 * n_boot)], 3), round(ts[int(0.975 * n_boot) - 1], 3)


def describe(values: list[float]) -> dict:
    v = sorted(values)
    return {"n": len(v), "min": round(v[0], 3), "p10": round(v[int(0.1 * (len(v) - 1))], 3),
            "median": round(statistics.median(v), 3), "max": round(v[-1], 3)}


def calibrate(pos: list[float], neg: list[float], name: str) -> dict:
    if len(pos) < 5 or len(neg) < 5:
        raise SystemExit(f"[✗] Trop peu de mesures pour calibrer le seuil {name} "
                         f"({len(pos)} positifs, {len(neg)} négatifs) : augmentez --n.")
    res = youden(pos, neg)
    res["bootstrap_95"] = bootstrap(pos, neg)
    res["positives"] = describe(pos)
    res["negatives"] = describe(neg)
    return res


def main():
    parser = argparse.ArgumentParser(description="Calibre les seuils du vérificateur causal sur la base de cas.")
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--n", type=int, default=20, help="nombre de paires (≈ 3 appels Mistral par paire)")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--cache", default="results/causal_calibration_pairs.jsonl")
    parser.add_argument("--output", default="results/causal_calibration.json")
    args = parser.parse_args()

    table = load_table(args.table)
    if not table:
        raise SystemExit(f"[✗] Table vide ou absente : {args.table}")
    pairs = build_pairs(table, args.n, args.seed)
    print(f"Table : {args.table} — {len(pairs)} paires (graine {args.seed})")

    done = {}
    if os.path.exists(args.cache):
        for row in read_jsonl(args.cache):
            done[row["pair"]] = row
        print(f"Reprise : {len(done)} paire(s) déjà traitée(s) dans {args.cache}")

    rem = Remediator()
    for n, (i, j, k) in enumerate(pairs, 1):
        key = f"{i['record_id']}|{j['record_id']}|{k['record_id']}"
        if key in done:
            continue
        print(f"[{n}/{len(pairs)}] {i['category']} : {i.get('source_paper')} -> {j.get('source_paper')}")
        chain_j, _ = rem.chain(j["attack_summary"])
        chain_k, _ = rem.chain(k["attack_summary"])
        source = {**i, "similarity_score": 1.0}
        recs, _ = rem.propose_adapt(j["attack_summary"], [source], chain_j)
        measures = []
        for rec in recs:
            action = (rec.get("action") or "").strip()
            if not action:
                continue
            link = normalize_link(rec.get("broken_link"))
            m = {"action": action, "broken_link": link,
                 "pos_sem": round(_cosine(rem.embed(action), rem.embed(i["mitigation_summary"])), 4),
                 "neg_sem": round(_cosine(rem.embed(action), rem.embed(k["mitigation_summary"])), 4),
                 "pos_link": None, "neg_link": None}
            if link in LINKS and chain_j.get(link) and chain_k.get(link):
                m["pos_link"] = round(_cosine(rem.embed(action), rem.embed(chain_j[link])), 4)
                m["neg_link"] = round(_cosine(rem.embed(action), rem.embed(chain_k[link])), 4)
            measures.append(m)
        row = {"pair": key, "category": i["category"], "negative_category": k["category"],
               "chain_target": chain_j, "chain_negative": chain_k, "measures": measures}
        append_jsonl(args.cache, row)
        done[key] = row
        print(f"    {len(measures)} mesure(s) : "
              + ", ".join(f"sém. {m['pos_sem']:.2f}/{m['neg_sem']:.2f}" for m in measures))

    rows = [done[f"{i['record_id']}|{j['record_id']}|{k['record_id']}"] for i, j, k in pairs]
    measures = [m for r in rows for m in r["measures"]]
    pos_sem = [m["pos_sem"] for m in measures]
    neg_sem = [m["neg_sem"] for m in measures]
    pos_link = [m["pos_link"] for m in measures if m["pos_link"] is not None]
    neg_link = [m["neg_link"] for m in measures if m["neg_link"] is not None]
    sem = calibrate(pos_sem, neg_sem, "sémantique")
    link = calibrate(pos_link, neg_link, "maillon")

    result = {
        "semantic_min": sem["threshold"],
        "link_min": link["threshold"],
        "table": args.table,
        "table_sha256": file_sha256(args.table),
        "seed": args.seed,
        "n_pairs": len(rows),
        "n_measures": len(measures),
        "semantic": sem,
        "link": link,
        "method": "Youden sur des paires de la base de cas (adaptation de la mitigation d'un cas à "
                  "l'attaque d'un autre cas de même technique) ; négatifs : cas d'une autre technique. "
                  "Aucune requête de test utilisée.",
    }
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    for name, r in (("Sémantique", sem), ("Maillon", link)):
        print(f"\n{name} : seuil = {r['threshold']} (IC bootstrap 95 % {r['bootstrap_95'][0]}–{r['bootstrap_95'][1]}), "
              f"TPR={r['tpr']}, TNR={r['tnr']}, exactitude équilibrée={r['balanced_accuracy']}")
        print(f"    positifs : {r['positives']}")
        print(f"    négatifs : {r['negatives']}")
        if r["balanced_accuracy"] < 0.6:
            print(f"    [⚠] seuil peu discriminant : à rapporter comme tel dans l'article")
    print(f"\n[✓] {args.output}  ->  python run_remediation.py ... --calibration {args.output}")


if __name__ == "__main__":
    main()
