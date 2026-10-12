"""
rescore_causal.py
------------------
Sensibilité de la Table IV aux seuils du vérificateur causal, SANS relancer
Mistral : les sorties de run_remediation.py enregistrent, pour chaque mesure,
le cosinus avec la mitigation citée (semantic_support) et avec le maillon
visé (link_similarity). On redécide l'acceptation pour une grille de seuils.

Ce script ne choisit AUCUN seuil : il montre comment les conclusions varient
(le seuil retenu vient de calibrate_causal.py, sur d'autres données).

Portée (à rappeler dans l'article) :
  - vérificateur "labels" seulement : pour "rule", le maillon a été déduit
    avec le seuil d'origine et n'est pas recalculable ;
  - "Retrieval, no loop" est exact : une seule proposition, redécidée ;
  - pour la boucle, la valeur est une APPROXIMATION : propositions initiales
    + mesures révisées acceptées au nouveau seuil, alors que la révision a
    été déclenchée par les rejets au seuil d'origine.
  - les mesures rejetées pour une autre raison (aucun cas cité, maillon
    "none" ou absent de la chaîne) restent rejetées.

Usage :
    python rescore_causal.py --results results/rq3_raw
    python rescore_causal.py --results results/rq3_raw --semantic 0.5 0.55 0.6 0.65 0.7 --link 0.4 0.5
"""

import argparse
import glob
import json
import os

from causal import LINKS


def accepted(rec: dict, chain: dict, semantic_min: float, link_min: float) -> bool:
    link = rec.get("broken_link_label")
    return (rec.get("cited") is not None
            and link in LINKS and bool(chain.get(link))
            and (rec.get("semantic_support") or 0) >= semantic_min
            and (rec.get("link_similarity") or 0) >= link_min)


def rescore_run(run: dict, semantic_min: float, link_min: float) -> list[dict]:
    """Mesures acceptées au seuil donné (dédoublonnage ignoré)."""
    if run.get("unanchored"):
        return []
    chain = run.get("chain") or {}
    recs = list(run.get("proposed") or [])
    if run.get("mode") == "retrieval_loop":
        recs += run.get("revised") or []
    return [r for r in recs if accepted(r, chain, semantic_min, link_min)]


def main():
    parser = argparse.ArgumentParser(description="Sensibilité de la Table IV aux seuils (sans Mistral).")
    parser.add_argument("--results", default="results/rq3_raw", help="dossier des remediation_*.json")
    parser.add_argument("--semantic", nargs="+", type=float, default=[0.5, 0.55, 0.6, 0.65, 0.7])
    parser.add_argument("--link", nargs="+", type=float, default=[0.5])
    parser.add_argument("--output", default=None, help="JSON de sortie (défaut : <results>/sensitivity.json)")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.results, "remediation_*.json")))
    if not files:
        raise SystemExit(f"[✗] Aucun remediation_*.json dans {args.results}")
    records = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            records.append(json.load(f))
    print(f"{len(records)} requêtes lues dans {args.results} "
          f"(seuils d'origine : sémantique={records[0].get('semantic_min')}, maillon={records[0].get('link_min')})")

    if not any(k.endswith("|labels") for r in records for k in r["runs"]):
        raise SystemExit("[✗] Aucun run « labels » dans ces fichiers (lancer avec --verifiers labels).")

    rows = []
    for mode in ("retrieval", "retrieval_loop"):
        key = f"{mode}|labels"
        for link_min in args.link:
            for semantic_min in args.semantic:
                n_in = q_in = n_ood = 0
                for rec in records:
                    run = rec["runs"].get(key)
                    if run is None:
                        continue
                    acc = rescore_run(run, semantic_min, link_min)
                    if rec["query"].get("in_corpus") is False:
                        n_ood += len(acc)
                    else:
                        n_in += len(acc)
                        q_in += bool(acc)
                rows.append({"mode": mode, "semantic_min": semantic_min, "link_min": link_min,
                             "accepted_in_corpus": n_in, "queries_served": q_in,
                             "n_in_corpus": sum(r["query"].get("in_corpus") is not False for r in records),
                             "accepted_ood": n_ood})

    print("\nMesures acceptées par le vérificateur labels selon les seuils "
          "(boucle : approximation, voir l'en-tête du script)")
    print(f"{'mode':15} {'sém.':>5} {'maillon':>7} {'acceptées':>9} {'requêtes servies':>17} {'hors corpus':>11}")
    for r in rows:
        print(f"{r['mode']:15} {r['semantic_min']:>5.2f} {r['link_min']:>7.2f} {r['accepted_in_corpus']:>9} "
              f"{str(r['queries_served']) + '/' + str(r['n_in_corpus']):>17} {r['accepted_ood']:>11}")

    out = args.output or os.path.join(args.results, "sensitivity.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"results": args.results, "rows": rows}, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] {out}")


if __name__ == "__main__":
    main()
