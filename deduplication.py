"""
deduplication.py
------------------
Limite le nombre de cas retenus par (papier, catégorie MITRE).

Le problème, mesuré sur Greshake et al. : 23 chunks sur 23 marqués
"attack_present", dont 18 avec la même catégorie AML.T0051.001 et des
résumés qui sont des paraphrases les uns des autres —

    "Indirect Prompt Injection allows adversaries to control LLM-integrated
     applications remotely"
    "Indirect Prompt Injection allows adversaries to control the behavior of
     LLMs in applications"
    "Indirect Prompt Injection (IPI) to compromise LLM-integrated applications"
    "Indirect Prompt Injection"

Ce ne sont pas 18 attaques : c'est une attaque décrite 18 fois. Un papier de
recherche reformule son sujet dans l'introduction, le related work, la
discussion et la conclusion, et Layer 2 traite chaque reformulation comme un
cas distinct. Même dérive que sur SoK/Backstabber's côté supply chain, mais
plus marquée ici parce que le papier entier porte sur UNE technique.

Conséquences concrètes si on ne filtre pas :
  - le retrieval (Step 6) renvoie dix quasi-doublons au lieu de dix cas
    différents — la table paraît riche mais ne couvre presque rien ;
  - les mitigations se dupliquent mécaniquement avec les attaques (10 des 12
    mitigations de Greshake sont des variantes d'une même phrase) ;
  - le corpus semble volumineux (29 enregistrements) alors qu'il contient une
    poignée de cas réels, ce qui fausserait toute statistique du mémoire.

La déduplication est appliquée AVANT le calcul des embeddings
(knowledge_table.build_table_from_methodology_records) : sur Greshake, 23
cas ramenés à ~6 économisent une trentaine d'appels Ollama par run.

NIVEAU 1 seulement (ce module) : plafonner le nombre de cas par catégorie et
garder les plus spécifiques. Le NIVEAU 2 — fusionner les résumés
sémantiquement redondants par similarité cosinus entre embeddings — est un
raffinement volontairement reporté : il coûte un embedding par cas AVANT de
savoir si on le garde, alors que le niveau 1 supprime déjà l'essentiel de la
redondance à coût nul.
"""

from specificity import is_specific_case

# Au-delà de ce nombre de cas pour une même catégorie DANS UN MÊME PAPIER, les
# suivants sont de la reformulation. Trois plutôt qu'un : un papier peut
# légitimement décrire deux ou trois variantes réellement différentes d'une
# même technique (chez Greshake, l'injection indirecte via page web, via
# document, et via plugin sont des cas distincts qui partagent AML.T0051.001).
MAX_CASES_PER_CATEGORY = 3

# Le plafond s'applique PAR PAPIER, jamais globalement : deux papiers qui
# décrivent la même technique apportent chacun leur point de vue, leurs
# systèmes visés et leurs défenses — c'est exactement ce qu'une base de
# connaissance doit contenir. C'est la répétition INTERNE à un papier qui est
# du bruit.


def _entities_in_summary(attack_summary: str, layer1_entities: list[dict]) -> int:
    """Nombre d'entités Layer 1 distinctes citées littéralement dans le résumé."""
    if not attack_summary:
        return 0
    text_lower = attack_summary.lower()
    return len(
        {
            e.get("text", "").strip().lower()
            for e in layer1_entities
            if e.get("text", "").strip()
            and e.get("text", "").strip().lower() in text_lower
        }
    )


def specificity_rank(
    record: dict, layer1_entities: list[dict], domain: str
) -> tuple:
    """
    Clé de tri décroissante : plus le tuple est grand, plus le cas mérite
    d'être gardé. Chaque composante répond à "lequel de ces deux résumés
    d'une même catégorie vaut-il mieux garder ?".

    1. cas concret (specificity.is_specific_case) — un cas qui nomme un
       système visé bat une reformulation générale, c'est le critère décisif ;
    2. porte une mitigation — un cas sans contre-mesure n'apporte rien au
       retrieval, dont le but est justement de proposer une remédiation ;
    3. nombre d'entités Layer 1 citées — mesure de l'ancrage factuel ;
    4. longueur du résumé, PLAFONNÉE à 40 mots — un résumé détaillé est
       préférable à "Indirect Prompt Injection" tout court, mais au-delà de
       deux phrases la longueur ne signale plus de la précision, seulement du
       délayage : sans plafond ce critère favoriserait le plus bavard ;
    5. confiance déclarée par le modèle — en dernier recours seulement, elle
       est peu discriminante en pratique (0.8 presque partout).
    """
    summary = record.get("attack_summary") or ""
    return (
        int(is_specific_case(summary, layer1_entities, domain)),
        int(bool(record.get("mitigation_summary"))),
        _entities_in_summary(summary, layer1_entities),
        min(len(summary.split()), 40),
        record.get("confidence") or 0.0,
    )


def deduplicate_by_category(
    methodology_records: list[dict],
    layer1_entities_per_chunk: list[list[dict]],
    domain: str,
    max_per_category: int = MAX_CASES_PER_CATEGORY,
) -> tuple[list[dict], list[list[dict]], dict]:
    """
    Ne garde que les `max_per_category` cas les plus spécifiques par
    catégorie, parmi les chunks où une attaque est confirmée.

    Renvoie (records gardés, entités correspondantes, {catégorie: nb écartés}).
    Les deux listes restent appariées index par index — le reste du pipeline
    en dépend (chaque record est scoré avec les entités de SON chunk).

    Les cas sans catégorie validée forment leur propre groupe et sont
    plafonnés pareil : ce sont typiquement les plus génériques ("Discussion of
    various attack techniques on Language Models"), donc ceux qu'il faut le
    moins laisser s'accumuler.

    L'ordre d'origine des chunks est préservé dans la sortie : la table reste
    lisible dans l'ordre du papier, et les record_id ne dépendent pas d'un
    ordre de tri interne.
    """
    confirmes = [
        i
        for i, record in enumerate(methodology_records)
        if record.get("attack_present")
    ]

    par_categorie: dict = {}
    for i in confirmes:
        par_categorie.setdefault(methodology_records[i].get("mitre_technique_id"), []).append(i)

    gardes: set = set()
    ecartes: dict = {}
    for categorie, indices in par_categorie.items():
        classes = sorted(
            indices,
            key=lambda i: specificity_rank(
                methodology_records[i], layer1_entities_per_chunk[i], domain
            ),
            reverse=True,
        )
        gardes.update(classes[:max_per_category])
        if len(classes) > max_per_category:
            ecartes[categorie] = len(classes) - max_per_category

    ordre = sorted(gardes)
    return (
        [methodology_records[i] for i in ordre],
        [layer1_entities_per_chunk[i] for i in ordre],
        ecartes,
    )


if __name__ == "__main__":
    # Reproduit la redondance réellement observée sur Greshake et al.
    records = [
        {"attack_present": True, "attack_summary": "Indirect Prompt Injection",
         "mitre_technique_id": "AML.T0051.001", "mitigation_summary": None, "confidence": 1.0},
        {"attack_present": True,
         "attack_summary": "Indirect Prompt Injection allows adversaries to control LLM-integrated applications remotely",
         "mitre_technique_id": "AML.T0051.001", "mitigation_summary": None, "confidence": 0.8},
        {"attack_present": True,
         "attack_summary": "A poisoned web page makes Bing Chat exfiltrate the chat history to the attacker.",
         "mitre_technique_id": "AML.T0051.001",
         "mitigation_summary": "The authors wrap retrieved content in explicit delimiters.", "confidence": 0.8},
        {"attack_present": True,
         "attack_summary": "Injected code in GitHub Copilot spreads when the user opens the package.",
         "mitre_technique_id": "AML.T0051.001",
         "mitigation_summary": "Filter code snippets included in the context.", "confidence": 0.8},
        {"attack_present": True, "attack_summary": "Indirect prompt injection to corrupt search queries",
         "mitre_technique_id": "AML.T0051.001", "mitigation_summary": None, "confidence": 0.8},
        {"attack_present": False, "attack_summary": None,
         "mitre_technique_id": None, "mitigation_summary": None, "confidence": 1.0},
    ]
    entities = [
        [],
        [],
        [{"text": "Bing Chat", "label": "application ou service intégrant un LLM"}],
        [{"text": "GitHub Copilot", "label": "application ou service intégrant un LLM"}],
        [],
        [],
    ]
    gardes, _, ecartes = deduplicate_by_category(records, entities, "llm")
    print(f"{len(records)} chunks -> {len(gardes)} cas gardés, écartés : {ecartes}\n")
    for r in gardes:
        print(f"  [{r['mitre_technique_id']}] {r['attack_summary']}")
