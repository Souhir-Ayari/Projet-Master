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

from config import DEFAULT_DOMAIN, DOMAIN_LLM, DOMAIN_SUPPLY_CHAIN

# Labels Layer 1 considérés comme "produit/fournisseur nommé" pour ce score,
# PAR DOMAINE — les taxonomies Layer 1 étant différentes, une liste unique
# serait silencieusement inopérante sur l'autre domaine (aucun label ne
# matcherait, donc TOUTES les mitigations noteraient 1.0 : un score constant
# qui aurait l'air de fonctionner).
#
# Volontairement restreint aux catégories qui désignent un produit/écosystème
# PROPRIÉTAIRE ou spécifique à un fournisseur — pas les identifiants
# génériques (CVE, dates) ni les standards ouverts type SLSA/Sigstore, qui
# sont eux-mêmes des mécanismes de mitigation généralisables plutôt que des
# produits verrouillés à un fournisseur.
VENDOR_ENTITY_LABELS_BY_DOMAIN = {
    # Menaces LLM : ce qui rend une défense NON portable, c'est qu'elle soit
    # formulée pour un modèle précis ("ajouter cette consigne au prompt
    # système de GPT-4") ou qu'elle repose sur l'outil maison des auteurs.
    # "défense ou garde-fou cité" en est EXCLU pour la même raison que SLSA
    # côté supply chain : un mécanisme de défense nommé (délimiteurs
    # explicites, classifieur de refus) est justement le genre de solution
    # généralisable que ce score doit récompenser, pas pénaliser — l'y mettre
    # ferait baisser la note de toute mitigation qui nomme sa propre méthode,
    # c'est-à-dire des meilleures. "vecteur d'entrée" et "impact sur le
    # modèle" en sont exclus aussi : ce sont des catégories du problème, pas
    # des dépendances de la solution.
    DOMAIN_LLM: frozenset(
        {
            "modèle LLM ciblé",
            "nom du système ou de l'attaque proposé par les auteurs",
        }
    ),
    DOMAIN_SUPPLY_CHAIN: frozenset(
        {
            "paquet ou bibliothèque logicielle concerné",
            "nom de logiciel ou produit",
            "distribution ou système affecté",
            "écosystème de composition logicielle cité",
            "système d'exploitation",
        }
    ),
}

# Conservé sous son ancien nom pour le code qui l'importait quand le pipeline
# ne traitait que la supply chain.
VENDOR_ENTITY_LABELS = VENDOR_ENTITY_LABELS_BY_DOMAIN[DOMAIN_SUPPLY_CHAIN]


def score_generalizability(
    mitigation_summary: str | None,
    layer1_entities: list[dict],
    domain: str = DEFAULT_DOMAIN,
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

    try:
        vendor_labels = VENDOR_ENTITY_LABELS_BY_DOMAIN[domain]
    except KeyError:
        raise ValueError(
            f"Domaine inconnu : {domain!r}. Domaines supportés : "
            f"{', '.join(sorted(VENDOR_ENTITY_LABELS_BY_DOMAIN))}"
        ) from None

    text_lower = mitigation_summary.lower()
    vendor_mentions = 0
    seen = set()
    for e in layer1_entities:
        if e.get("label") not in vendor_labels:
            continue
        entity_text = e.get("text", "").strip().lower()
        if not entity_text or entity_text in seen:
            continue
        if entity_text in text_lower:
            vendor_mentions += 1
            seen.add(entity_text)

    return round(1.0 / (1 + vendor_mentions), 4)


if __name__ == "__main__":
    llm_entities = [
        {"text": "GPT-4", "label": "modèle LLM ciblé"},
        {"text": "prompt utilisateur", "label": "vecteur d'entrée"},  # pas un vendor
    ]
    print(
        score_generalizability(
            "Encadrer le contenu récupéré par des délimiteurs explicites et "
            "répéter les consignes système après lui.",
            llm_entities,
        )
    )  # défense portable, aucun modèle nommé -> 1.0
    print(
        score_generalizability(
            "Ajouter la consigne de refus au prompt système de GPT-4.",
            llm_entities,
        )
    )  # dépend d'un modèle nommé -> 0.5

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
            DOMAIN_SUPPLY_CHAIN,
        )
    )  # aucune mention vendor -> 1.0
    print(
        score_generalizability(
            "Azure Verified Modules et Debian montrent l'intérêt d'une gouvernance stricte.",
            entities,
            DOMAIN_SUPPLY_CHAIN,
        )
    )  # 2 mentions -> 0.333
    print(score_generalizability(None, entities, DOMAIN_SUPPLY_CHAIN))  # None
