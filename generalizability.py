"""
generalizability.py
--------------------
Step 4 du pipeline méthodologie/mitigation : score de généralisabilité d'une
mitigation. Version volontairement simple et reproductible (demandée en
priorité) : compte les entités de type produit/fournisseur/écosystème DÉJÀ
extraites par Layer 1 pour ce même chunk qui apparaissent dans le texte de
mitigation_summary — plus une mitigation nomme d'éléments propriétaires
spécifiques, moins elle est généralisable à d'autres contextes.

La version notée par un LLM avec auto-cohérence (génération x2, accord à ±1
point, taux d'accord reporté comme résultat) est un TRAVAIL FUTUR documenté
mais volontairement non implémenté ici : elle ajoute un aller-retour LLM de
plus par mitigation, à faire seulement une fois la version simple validée.
"""

# Labels Layer 1 considérés comme "produit/fournisseur nommé" pour ce score.
# Volontairement restreint aux catégories qui désignent un produit/écosystème
# PROPRIÉTAIRE ou spécifique à un fournisseur — pas les identifiants
# génériques (CVE, dates) ni les standards ouverts type SLSA/Sigstore, qui
# sont eux-mêmes des mécanismes de mitigation généralisables plutôt que des
# produits verrouillés à un fournisseur.
VENDOR_ENTITY_LABELS = frozenset(
    {
        "paquet ou bibliothèque logicielle concerné",
        "nom de logiciel ou produit",
        "distribution ou système affecté",
        "écosystème de composition logicielle cité",
        "système d'exploitation",
    }
)


def score_generalizability(
    mitigation_summary: str | None, layer1_entities: list[dict]
) -> float | None:
    """
    Renvoie None si mitigation_summary est absent — rien à noter, cohérent
    avec les "honest nulls" du Step 3 : pas de score inventé pour une
    mitigation qui n'existe pas. Sinon un score dans ]0, 1] : 1.0 si aucune
    mention de produit/fournisseur nommé (mitigation générale, portable à
    d'autres contextes), décroissant avec leur nombre.
    """
    if not mitigation_summary:
        return None

    text_lower = mitigation_summary.lower()
    vendor_mentions = 0
    seen = set()
    for e in layer1_entities:
        if e.get("label") not in VENDOR_ENTITY_LABELS:
            continue
        entity_text = e.get("text", "").strip().lower()
        if not entity_text or entity_text in seen:
            continue
        if entity_text in text_lower:
            vendor_mentions += 1
            seen.add(entity_text)

    return round(1.0 / (1 + vendor_mentions), 4)


if __name__ == "__main__":
    entities = [
        {
            "text": "Azure Verified Modules",
            "label": "écosystème de composition logicielle cité",
        },
        {"text": "SLSA", "label": "framework ou mécanisme de mitigation"},  # standard ouvert, pas compté
        {"text": "Debian", "label": "distribution ou système affecté"},
    ]
    print(
        score_generalizability(
            "L'utilisation de SLSA pour la provenance des artefacts est recommandée.",
            entities,
        )
    )  # aucune mention vendor -> 1.0
    print(
        score_generalizability(
            "Azure Verified Modules et Debian montrent l'intérêt d'une gouvernance stricte.",
            entities,
        )
    )  # 2 mentions -> 0.333
    print(score_generalizability(None, entities))  # None
