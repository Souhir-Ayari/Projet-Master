"""
specificity.py
----------------
Distingue un cas d'attaque CONCRET (identifiable : nom de paquet, CVE,
date...) d'une reformulation GÉNÉRIQUE du sujet du papier. Constaté sur les
papers de synthèse (SoK, Backstabber's Knife Collection) : l'intro/la
discussion reformule "ce dataset/cette taxonomie traite des attaques de la
supply chain" à plusieurs endroits du texte, et Layer 2 traite chacune de
ces reformulations comme une "attaque confirmée" distincte — même famille de
problème que la sur-extraction de phrases descriptives à Layer 1 (déjà
filtrée par la longueur, voir mistral_extractor._filter_by_length), mais qui
réapparaît ici au niveau du CAS complet plutôt que d'une entité isolée.

Les cas génériques ne sont PAS supprimés (ils peuvent rester utiles comme
contexte de taxonomie) mais sont marqués distinctement (specificity:
"generic" vs "concrete") pour que le retrieval (Step 6) puisse privilégier
les cas concrets sans que ce soit noyé dans le bruit.

Le même problème se pose sur le corpus "menaces LLM" — les papers de synthèse
y reformulent "l'injection de prompt contourne l'alignement du modèle" à
chaque section — d'où une liste de labels identifiants PAR DOMAINE plutôt
qu'une seule liste supply-chain.
"""

from config import DEFAULT_DOMAIN, DOMAIN_LLM, DOMAIN_SUPPLY_CHAIN

# Labels Layer 1 considérés comme des identifiants "durs" d'une instance
# d'attaque précise plutôt que d'une catégorie générique — un par domaine
# d'analyse, chacun restreint à ce qui existe RÉELLEMENT dans la taxonomie
# passée à GLiNER pour CE domaine (voir config.TOPIC_DOMAINS). Un label absent
# de la taxonomie réellement utilisée ne matcherait jamais rien : le filtre
# serait silencieusement inopérant et TOUS les cas seraient marqués
# "generic". C'est exactement le piège rencontré la première fois avec "nom de
# malware" / "acteur de menace (APT)", qui appartiennent à CYBER_ENTITY_LABELS
# (taxonomie générique de main.py) et non à SUPPLY_CHAIN_ENTITY_LABELS.
SPECIFIC_ENTITY_LABELS_BY_DOMAIN = {
    # Menaces LLM : ce qui distingue un CAS d'attaque réel d'une reformulation
    # du sujet, c'est qu'un NOM PROPRE soit cité — le modèle visé, le service
    # attaqué (Bing Chat, Copilot...), la défense ou l'attaque nommée par les
    # auteurs. Seuls des labels concrets figurent ici : les axes analytiques
    # du sujet ("vecteur d'entrée", "mécanisme de contournement", "impact sur
    # le modèle") en sont EXCLUS, parce qu'ils décrivent des catégories
    # ("prompt utilisateur", "fuite de données") présentes dans à peu près
    # toute phrase générale du domaine — sans pouvoir discriminant.
    DOMAIN_LLM: frozenset(
        {
            "modèle LLM ciblé",
            "application ou service intégrant un LLM",
            "défense ou garde-fou cité",
            "nom du système ou de l'attaque proposé par les auteurs",
        }
    ),
    DOMAIN_SUPPLY_CHAIN: frozenset(
        {
            "identifiant CVE",
            "paquet ou bibliothèque logicielle concerné",
            "année ou période de l'incident",
            "organisation ayant analysé l'incident",
            "service ou composant ciblé",
            "distribution ou système affecté",
        }
    ),
}

# Conservé pour compatibilité avec le code (et les notebooks d'analyse) qui
# importaient ce nom du temps où le pipeline ne traitait que la supply chain.
SPECIFIC_ENTITY_LABELS = SPECIFIC_ENTITY_LABELS_BY_DOMAIN[DOMAIN_SUPPLY_CHAIN]


def is_specific_case(
    attack_summary: str | None,
    layer1_entities: list[dict],
    domain: str = DEFAULT_DOMAIN,
) -> bool:
    """
    Un cas est retenu comme instance CONCRÈTE seulement s'il mentionne, dans
    son propre texte, au moins une entité Layer 1 identifiante — pas juste
    "détectée quelque part dans le chunk" : l'entité doit apparaître
    littéralement dans attack_summary lui-même, pour s'assurer que le résumé
    PARLE bien de ce cas précis plutôt que d'être une reformulation générale
    du sujet, à côté d'entités sans rapport ailleurs dans le même chunk.
    """
    if not attack_summary:
        return False
    try:
        specific_labels = SPECIFIC_ENTITY_LABELS_BY_DOMAIN[domain]
    except KeyError:
        raise ValueError(
            f"Domaine inconnu : {domain!r}. Domaines supportés : "
            f"{', '.join(sorted(SPECIFIC_ENTITY_LABELS_BY_DOMAIN))}"
        ) from None
    text_lower = attack_summary.lower()
    return any(
        e.get("label") in specific_labels
        and e.get("text", "").strip()
        and e.get("text", "").strip().lower() in text_lower
        for e in layer1_entities
    )


if __name__ == "__main__":
    llm_entities = [
        {"text": "GPT-4", "label": "modèle LLM ciblé"},
        {"text": "leak the system prompt", "label": "impact sur le modèle"},
        {"text": "prompt utilisateur", "label": "vecteur d'entrée"},  # pas identifiant
    ]
    print(
        is_specific_case(
            "The attack makes GPT-4 leak the system prompt through a crafted "
            "conversation turn.",
            llm_entities,
        )
    )  # True : "GPT-4" (modèle ciblé) apparaît dans le résumé
    print(
        is_specific_case(
            "Prompt injection allows an attacker to bypass the model's alignment.",
            llm_entities,
        )
    )  # False : reformulation générale, aucune entité identifiante dans ce texte

    entities = [
        {"text": "event-stream", "label": "paquet ou bibliothèque logicielle concerné"},
        {"text": "CVE-2021-44228", "label": "identifiant CVE"},
        {
            "text": "SLSA",
            "label": "framework ou mécanisme de mitigation",
        },  # pas un identifiant "dur"
    ]
    print(
        is_specific_case(
            "An attack on the npm package event-stream involved the alleged "
            "attacker gaining ownership by taking over maintenance.",
            entities,
            DOMAIN_SUPPLY_CHAIN,
        )
    )  # True : "event-stream" apparaît dans le résumé
    print(
        is_specific_case(
            "Malicious packages used in real-world attacks",
            entities,
            DOMAIN_SUPPLY_CHAIN,
        )
    )  # False : aucune entité identifiante dans ce texte générique
