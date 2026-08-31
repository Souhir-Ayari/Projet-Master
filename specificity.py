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
"""

# Labels Layer 1 considérés comme des identifiants "durs" d'une instance
# d'attaque précise plutôt que d'une catégorie générique. Restreint à ce qui
# existe RÉELLEMENT dans config.SUPPLY_CHAIN_ENTITY_LABELS — c'est cette
# taxonomie que GLiNER utilise dans build_knowledge.py. "nom de malware" et
# "acteur de menace (APT)" (proposés initialement) n'en font PAS partie : ce
# sont des labels de CYBER_ENTITY_LABELS, la taxonomie générique utilisée
# ailleurs dans le pipeline (main.py), jamais celle passée à GLiNER ici — un
# filtre qui les chercherait ne matcherait donc jamais rien.
SPECIFIC_ENTITY_LABELS = frozenset(
    {
        "identifiant CVE",
        "paquet ou bibliothèque logicielle concerné",
        "année ou période de l'incident",
        "organisation ayant analysé l'incident",
        "service ou composant ciblé",
        "distribution ou système affecté",
    }
)


def is_specific_case(attack_summary: str | None, layer1_entities: list[dict]) -> bool:
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
    text_lower = attack_summary.lower()
    return any(
        e.get("label") in SPECIFIC_ENTITY_LABELS
        and e.get("text", "").strip()
        and e.get("text", "").strip().lower() in text_lower
        for e in layer1_entities
    )


if __name__ == "__main__":
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
        )
    )  # True : "event-stream" apparaît dans le résumé
    print(
        is_specific_case("Malicious packages used in real-world attacks", entities)
    )  # False : aucune entité identifiante dans ce texte générique
