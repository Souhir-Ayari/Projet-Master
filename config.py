"""
config.py
---------
Configuration centrale du projet : labels d'entités pour GLiNER (NER zero-shot)
et templates de prompts pour Mistral 7B (extraction prompt-based).

Modifier ce fichier pour ajuster les entités ciblées ou affiner les prompts
sans toucher au reste du code.
"""

import re

# ---------------------------------------------------------------------------
# 1) LABELS D'ENTITÉS CYBERSÉCURITÉ (utilisés par GLiNER en zero-shot)
# ---------------------------------------------------------------------------
# GLiNER accepte des labels arbitraires en langage naturel : plus le label
# est explicite, meilleure est la détection zero-shot. On reste volontairement
# concis ici (2-5 mots par label) car GLiNER fonctionne mieux avec des labels
# courts et proches du vocabulaire NER standard ; les précisions détaillées
# vont dans ENTITY_DESCRIPTIONS ci-dessous (utilisées uniquement pour Mistral).
#
# Par rapport à la première version, ces labels sont plus GRANULAIRES :
# les hash sont séparés par type (MD5/SHA1/SHA256 n'ont pas la même longueur,
# les confondre est une source d'erreur), la vulnérabilité générique est
# scindée en CVE (identifiant officiel) et CWE (catégorie de faiblesse), et
# on ajoute le contexte de l'attaque (secteur, pays, vecteur initial,
# mitigation) qui manquait pour une analyse de threat intelligence complète.
CYBER_ENTITY_LABELS = [
    "adresse IP",
    "nom de domaine",
    "URL malveillante",
    "adresse email",
    "identifiant CVE",
    "identifiant CWE",
    "nom de malware",
    "acteur de menace (APT)",
    "hash MD5",
    "hash SHA1",
    "hash SHA256",
    "technique MITRE ATT&CK",
    "nom de logiciel ou produit",
    "version de logiciel",
    "système d'exploitation",
    "organisation victime",
    "secteur d'activité ciblé",
    "pays ou région ciblée",
    "port réseau",
    "protocole réseau",
    "date de l'incident",
    "vecteur d'attaque initial",
    "mesure de mitigation",
]

# ---------------------------------------------------------------------------
# 1bis) DESCRIPTIONS DÉTAILLÉES (utilisées uniquement dans les prompts Mistral)
# ---------------------------------------------------------------------------
# Ces descriptions ne sont PAS envoyées à GLiNER (qui reste sur les labels
# courts ci-dessus). Elles sont injectées dans les prompts "engineered" et
# "custom" de Mistral pour lever les ambiguïtés : un LLM guidé par un exemple
# concret de format ("32 caractères hexadécimaux") hallucine beaucoup moins
# qu'un LLM guidé par un simple nom de catégorie.
ENTITY_DESCRIPTIONS = {
    "adresse IP": "adresse IPv4 ou IPv6 exacte, ex: 0.0.0.0 (valeur FICTIVE, format uniquement)",
    "nom de domaine": "nom de domaine complet (FQDN), sans http(s)://, ex: exemple-fictif.test (valeur FICTIVE)",
    "URL malveillante": "URL complète avec schéma, ex: hxxp://exemple-fictif.test/page (valeur FICTIVE)",
    "adresse email": "adresse email complète avec @ (aucun exemple fourni, format uniquement)",
    "identifiant CVE": "format officiel CVE-AAAA-NNNNN, ex: CVE-0000-00000 (valeur FICTIVE, format uniquement)",
    "identifiant CWE": "format officiel CWE-NNN, ex: CWE-000 (valeur FICTIVE, format uniquement)",
    "nom de malware": "nom propre du malware ou de la famille (aucun exemple fourni, pour éviter toute confusion avec une vraie famille de malware)",
    "acteur de menace (APT)": "nom du groupe ou de l'acteur (aucun exemple fourni, pour éviter toute confusion avec un vrai groupe APT)",
    "hash MD5": "chaîne hexadécimale de EXACTEMENT 32 caractères (aucun exemple fourni, format uniquement)",
    "hash SHA1": "chaîne hexadécimale de EXACTEMENT 40 caractères (aucun exemple fourni, format uniquement)",
    "hash SHA256": "chaîne hexadécimale de EXACTEMENT 64 caractères (aucun exemple fourni, format uniquement)",
    "technique MITRE ATT&CK": "identifiant officiel Txxxx ou Txxxx.xxx, ex: T0000.000 (valeur FICTIVE, format uniquement)",
    "nom de logiciel ou produit": "nom du produit/logiciel concerné, SANS le numéro de version (aucun exemple fourni)",
    "version de logiciel": "numéro de version exact cité, format X.Y.Z (aucun exemple chiffré fourni, format uniquement)",
    "système d'exploitation": "OS et éventuellement sa version (aucun exemple fourni, format uniquement)",
    "organisation victime": "nom propre de l'entreprise ou institution ciblée par l'attaque (aucun exemple fourni)",
    "secteur d'activité ciblé": "secteur économique (ex: type de catégorie comme « santé » ou « finance » — exemples de CATÉGORIES génériques, pas des faits à reprendre)",
    "pays ou région ciblée": "nom du pays ou de la région géographique concernée (aucun exemple fourni)",
    "port réseau": "numéro de port réseau (aucun exemple chiffré fourni, format uniquement)",
    "protocole réseau": "nom du protocole (ex: type de catégorie comme « RDP » ou « HTTP » — exemples de CATÉGORIES génériques, pas des faits à reprendre)",
    "date de l'incident": "date au format le plus précis disponible dans le texte source",
    "vecteur d'attaque initial": "méthode d'accès initial citée (ex: type de catégorie comme « phishing » ou « brute-force » — exemples de CATÉGORIES génériques, pas des faits à reprendre)",
    "mesure de mitigation": "action corrective ou recommandation explicitement citée dans le texte",
}


def build_labels_block(labels: list[str] = None, descriptions: dict = None) -> str:
    """
    Construit le bloc de labels injecté dans les prompts Mistral, en
    combinant chaque label avec sa description quand elle existe
    (format "- label : description"). C'est cette version enrichie qui
    remplace la simple liste à puces utilisée dans la première itération
    du projet, pour une extraction plus précise et moins ambiguë.

    `descriptions` permet d'utiliser un dictionnaire de descriptions différent
    de ENTITY_DESCRIPTIONS (par défaut) — utile pour la taxonomie
    SUPPLY_CHAIN_ENTITY_LABELS avec SUPPLY_CHAIN_ENTITY_DESCRIPTIONS.
    """
    labels = labels or CYBER_ENTITY_LABELS
    descriptions = descriptions if descriptions is not None else ENTITY_DESCRIPTIONS
    lines = []
    for label in labels:
        description = descriptions.get(label)
        lines.append(f"- {label} : {description}" if description else f"- {label}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1ter) PATTERNS DE VALIDATION DE FORMAT (couche de précision supplémentaire)
# ---------------------------------------------------------------------------
# Certaines catégories ont un format strict et vérifiable. Ces regex servent
# de garde-fou POST-EXTRACTION (voir evaluator.py -> compute_format_violations) :
# une entité dont le label est "identifiant CVE" mais dont le texte ne
# respecte pas CVE-AAAA-NNNNN est très probablement une hallucination ou une
# erreur de parsing, même si elle n'est pas détectée par la simple vérification
# de présence littérale dans le texte source.
ENTITY_REGEX_PATTERNS = {
    "identifiant CVE": re.compile(r"^CVE-\d{4}-\d{4,7}$", re.IGNORECASE),
    "identifiant CWE": re.compile(r"^CWE-\d{1,4}$", re.IGNORECASE),
    "hash MD5": re.compile(r"^[a-fA-F0-9]{32}$"),
    "hash SHA1": re.compile(r"^[a-fA-F0-9]{40}$"),
    "hash SHA256": re.compile(r"^[a-fA-F0-9]{64}$"),
    "adresse IP": re.compile(r"^(\d{1,3}\.){3}\d{1,3}$"),
    "technique MITRE ATT&CK": re.compile(r"^T\d{4}(\.\d{3})?$", re.IGNORECASE),
    "port réseau": re.compile(r"^\d{1,5}$"),
}


def is_format_valid(label: str, text: str) -> bool | None:
    """
    Vérifie si le texte extrait respecte le format attendu pour ce label.
    Renvoie None si aucun pattern n'est défini pour ce label (catégories
    textuelles libres comme "organisation victime", où aucun format fixe
    n'existe et donc aucune vérification structurelle n'est possible).
    """
    pattern = ENTITY_REGEX_PATTERNS.get(label)
    if pattern is None:
        return None
    return bool(pattern.match(text.strip()))


# ---------------------------------------------------------------------------
# 1quater) LABELS SPÉCIFIQUES AU SUJET : ATTAQUES DE LA CHAÎNE D'APPROVISIONNEMENT
#          LOGICIELLE / BACKDOORS DANS LES DÉPÔTS OPEN SOURCE
# ---------------------------------------------------------------------------
# Contrairement à CYBER_ENTITY_LABELS (générique, utilisé par GLiNER en CAS 1
# ET par défaut pour Mistral en CAS 2), cette taxonomie est volontairement
# étroite et calée sur UN sujet précis : les compromissions de chaîne
# d'approvisionnement logicielle type XZ Utils / SolarWinds / Log4Shell.
# Elle sert exclusivement au prompt "topic" (voir PROMPT_TOPIC_SUPPLY_CHAIN
# ci-dessous), pour mesurer si un prompt spécialisé sur le sujet exact du
# document améliore la précision par rapport au NER généraliste du CAS 1.
SUPPLY_CHAIN_ENTITY_LABELS = [
    "paquet ou bibliothèque logicielle concerné",
    "identifiant CVE",
    "service ou composant ciblé",
    "distribution ou système affecté",
    "nombre de systèmes ou paquets impactés",
    "vecteur d'attaque ou méthode d'infiltration",
    "année ou période de l'incident",
    "organisation ayant analysé l'incident",
    "framework ou mécanisme de mitigation",
    "nom du système ou framework proposé par les auteurs",
    "système formellement vérifié cité en comparaison",
    "écosystème de composition logicielle cité",
]

SUPPLY_CHAIN_ENTITY_DESCRIPTIONS = {
    "paquet ou bibliothèque logicielle concerné": "nom du logiciel/bibliothèque touché par l'attaque (aucun exemple fourni, pour éviter toute confusion avec un vrai paquet)",
    "identifiant CVE": "format officiel CVE-AAAA-NNNNN, ex: CVE-0000-000043 (valeur FICTIVE, format uniquement)",
    "service ou composant ciblé": "processus ou service visé par le code malveillant (aucun exemple fourni)",
    "distribution ou système affecté": "distribution Linux ou plateforme touchée (aucun exemple fourni)",
    "nombre de systèmes ou paquets impactés": "chiffre d'impact cité dans le texte (aucun exemple chiffré fourni, format uniquement)",
    "vecteur d'attaque ou méthode d'infiltration": "méthode utilisée par l'attaquant (ex: type de catégorie comme « ingénierie sociale » ou « script de build modifié » — exemples de CATÉGORIES génériques, pas des faits à reprendre)",
    "année ou période de l'incident": "année ou intervalle temporel cité dans le texte (aucun exemple chiffré fourni)",
    "organisation ayant analysé l'incident": "entreprise ou équipe de recherche ayant documenté l'attaque (aucun exemple fourni)",
    "framework ou mécanisme de mitigation": "solution ou norme de sécurité citée (aucun exemple fourni, pour éviter toute confusion avec un vrai framework)",
    "nom du système ou framework proposé par les auteurs": "nom du système/modèle proposé par les auteurs du document analysé (aucun exemple fourni)",
    "système formellement vérifié cité en comparaison": "exemple de système à correction prouvée mentionné dans le texte (aucun exemple fourni)",
    "écosystème de composition logicielle cité": "plateforme de composition logicielle citée dans le texte (aucun exemple fourni)",
}

# ---------------------------------------------------------------------------
# 2) SCHEMA JSON DE SORTIE COMMUN AUX DEUX PIPELINES
# ---------------------------------------------------------------------------
# On force le même schéma pour GLiNER et Mistral afin que l'évaluation
# (comparaison des JSON) soit équitable.
OUTPUT_SCHEMA_EXAMPLE = {
    "entities": [
        {
            "text": "0.0.0.0",
            "label": "adresse IP",
            "start": 0,
            "end": 0,
        }  # valeur FICTIVE, exemple de structure uniquement
    ]
}

# ---------------------------------------------------------------------------
# 3) PROMPTS POUR MISTRAL 7B (CAS 2 : prompt-based extraction)
# ---------------------------------------------------------------------------
# On garde plusieurs variantes pour pouvoir mesurer l'effet du prompt engineering
# comme demandé : PROMPT_NAIVE (référence basse) vs PROMPT_NAIVE_SCHEMA
# (référence intermédiaire) vs PROMPT_ENGINEERED (optimisé).

PROMPT_NAIVE = """Extrais les entités importantes de ce texte de cybersécurité.

Réponds uniquement avec un JSON valide, sans texte avant/après, au format :
{{"entities": [{{"text": "...", "label": "..."}}]}}

Texte:
{text}
json :"""


# PROMPT_NAIVE_SCHEMA : variante intermédiaire entre naive et engineered.
# PROMPT_NAIVE ne précise ni catégories ni schéma JSON -> le modèle échoue
# souvent à produire un JSON exploitable (0 entité extraite), ce qui biaise
# la comparaison : on ne sait pas si le gain d'engineered vient du schéma
# JSON imposé, ou des règles anti-hallucination, car les DEUX changent en
# même temps entre naive et engineered. PROMPT_NAIVE_SCHEMA isole UNE seule
# variable (le schéma + les catégories, mais SANS règles anti-hallucination)
# pour permettre une comparaison à 3 points propre dans le mémoire :
#   naive (rien) -> naive_schema (format seul) -> engineered (format + anti-hallucination)
# Si naive_schema améliore déjà beaucoup le F1 par rapport à naive, le gain
# vient surtout du format. Si le vrai saut se voit entre naive_schema et
# engineered, le gain vient surtout des règles anti-hallucination.
PROMPT_NAIVE_SCHEMA = """Extrais les entités importantes de ce texte de cybersécurité.

Catégories possibles :
{labels}

Réponds uniquement avec un JSON au format :
{{"entities": [{{"text": "...", "label": "..."}}]}}

Texte:
{text}

json : 
"""

PROMPT_ENGINEERED = """Tu es un analyste SOC (Security Operations Center) expert en threat intelligence.
Ta tâche est d'extraire UNIQUEMENT les entités explicitement présentes dans le texte
ci-dessous, sans en inventer aucune (zéro hallucination).

Catégories d'entités à extraire :
{labels}

Règles strictes :
1. N'extrais que du texte qui apparaît mot pour mot dans le document source.
2. Si une catégorie n'a aucune occurrence, ne l'inclus pas.
3. Ne déduis pas, n'infère pas, ne complète pas d'information manquante.
4. Ignore complètement toute section "References", "Bibliography", liste de citations
   numérotées ([1], [2]...), URL de type DOI, ou métadonnées de publication (auteurs,
   dates de conférence). Ce ne sont jamais des entités valides même si elles contiennent
   des mots-clés cybersécurité.
5. N'utilise jamais de texte de remplissage ("non spécifié", "N/A", "unknown", "aucun").
   Si une catégorie n'a pas d'occurrence, omets-la simplement — ne mets aucune entrée.
6. Réponds UNIQUEMENT avec un JSON valide, sans texte avant/après, au format exact :

{{
  "entities": [
    {{"text": "<extrait exact du texte>", "label": "<une des catégories ci-dessus>"}}
  ]
}}

Exemple (valeurs FICTIVES, uniquement pour illustrer le FORMAT — ne jamais les recopier) :
Texte : "L'attaquant a utilisé l'IP 0.0.0.0 pour exploiter CVE-0000-00000."
Sortie :
{{
  "entities": [
    {{"text": "0.0.0.0", "label": "adresse IP"}},
    {{"text": "CVE-0000-00000", "label": "identifiant CVE"}}
  ]
}}

RÈGLE SUPPLÉMENTAIRE : l'exemple ci-dessus illustre uniquement le FORMAT JSON attendu.
Ses valeurs (0.0.0.0, CVE-0000-00000) sont fictives : ne les inclus JAMAIS dans ta réponse,
même si elles semblent plausibles.

Texte à analyser :
\"\"\"
{text}
\"\"\"

JSON :"""

PROMPT_CUSTOM = """Tu es un analyste SOC (Security Operations Center) expert en threat intelligence.
Un utilisateur a un besoin d'extraction SPÉCIFIQUE (plus ciblé qu'une simple liste
générique de catégories NER). Ta mission est de répondre précisément à CE besoin,
et uniquement à celui-ci.

Besoin exprimé par l'utilisateur :
\"\"\"
{user_need}
\"\"\"

Catégories générales de référence (à utiliser seulement si elles aident à répondre
au besoin ci-dessus ; ignore celles qui ne sont pas pertinentes pour la demande) :
{labels}

Règles strictes (anti-hallucination) :
1. Concentre-toi exclusivement sur ce que l'utilisateur demande dans "Besoin exprimé".
2. N'extrais que du texte qui apparaît mot pour mot dans le document source.
3. Si le besoin de l'utilisateur ne correspond à rien dans le texte, renvoie une liste vide.
4. Ne déduis pas, n'infère pas, ne complète pas d'information manquante.
5. Ignore complètement toute section "References", "Bibliography", liste de citations
   numérotées ([1], [2]...), URL de type DOI, ou métadonnées de publication (auteurs,
   dates de conférence). Ce ne sont jamais des entités valides même si elles contiennent
   des mots-clés cybersécurité.
6. N'utilise jamais de texte de remplissage ("non spécifié", "N/A", "unknown", "aucun").
   Si une catégorie n'a pas d'occurrence, omets-la simplement — ne mets aucune entrée.
7. Avant de répondre, identifie explicitement les 2-3 catégories de {labels} qui
   correspondent RÉELLEMENT au besoin exprimé. N'utilise QUE ces catégories dans ta
   réponse finale — même si d'autres entités intéressantes apparaissent dans le texte.
8. Réponds UNIQUEMENT avec un JSON valide, sans texte avant/après, au format exact
   (le champ "relevant_categories" doit contenir les 2-3 catégories identifiées
   à la règle 7 — c'est ce qui permet de vérifier que tu les as bien respectées) :

{{
  "relevant_categories": ["<catégorie 1>", "<catégorie 2>"],
  "entities": [
    {{"text": "<extrait exact du texte>", "label": "<une des catégories de relevant_categories>"}}
  ]
}}

Texte à analyser :
\"\"\"
{text}
\"\"\"

JSON :"""

# PROMPT_TOPIC_SUPPLY_CHAIN : prompt "engineered" spécialisé, calé sur la
# taxonomie étroite SUPPLY_CHAIN_ENTITY_LABELS (au lieu de CYBER_ENTITY_LABELS)
# et sur le vocabulaire des attaques de chaîne d'approvisionnement logicielle
# (XZ Utils, SolarWinds, Log4Shell). Utilisé par prompt_variant == "topic"
# dans mistral_extractor.MistralExtractor.extract().
PROMPT_TOPIC_SUPPLY_CHAIN = """Tu es un analyste SOC (Security Operations Center) expert en compromissions de
chaîne d'approvisionnement logicielle (supply chain attacks / backdoors dans des
dépôts open source, type XZ Utils, SolarWinds, Log4Shell).
Ta tâche est d'extraire UNIQUEMENT les entités explicitement présentes dans le texte
ci-dessous, sans en inventer aucune (zéro hallucination).

Catégories d'entités à extraire (spécifiques aux attaques de chaîne d'approvisionnement) :
{labels}

Règles strictes :
1. N'extrais que du texte qui apparaît mot pour mot dans le document source.
2. Si une catégorie n'a aucune occurrence, ne l'inclus pas.
3. Ne déduis pas, n'infère pas, ne complète pas d'information manquante.
4. Ignore complètement toute section "References", "Bibliography", liste de citations
   numérotées ([1], [2]...), URL de type DOI, ou métadonnées de publication (auteurs,
   dates de conférence). Ce ne sont jamais des entités valides même si elles contiennent
   des mots-clés cybersécurité.
5. N'utilise jamais de texte de remplissage ("non spécifié", "N/A", "unknown", "aucun").
   Si une catégorie n'a pas d'occurrence, omets-la simplement — ne mets aucune entrée.
6. Réponds UNIQUEMENT avec un JSON valide, sans texte avant/après, au format exact :

{{
  "entities": [
    {{"text": "<extrait exact du texte>", "label": "<une des catégories ci-dessus>"}}
  ]
}}

Exemple (valeurs FICTIVES, uniquement pour illustrer le FORMAT — ne jamais les recopier) :
Texte : "Le paquet libexemple-fictif a été compromis, ce qui correspond à CVE-0000-000043."
Sortie :
{{
  "entities": [
    {{"text": "libexemple-fictif", "label": "paquet ou bibliothèque logicielle concerné"}},
    {{"text": "CVE-0000-000043", "label": "identifiant CVE"}}
  ]
}}

RÈGLE SUPPLÉMENTAIRE : l'exemple ci-dessus illustre uniquement le FORMAT JSON attendu.
Ses valeurs (libexemple-fictif, CVE-0000-000043) sont fictives : ne les inclus JAMAIS
dans ta réponse, même si elles semblent plausibles.

Texte à analyser :
\"\"\"
{text}
\"\"\"

JSON :"""


PROMPTS = {
    "naive": PROMPT_NAIVE,
    "naive_schema": PROMPT_NAIVE_SCHEMA,
    "engineered": PROMPT_ENGINEERED,
    "custom": PROMPT_CUSTOM,
    "topic": PROMPT_TOPIC_SUPPLY_CHAIN,
}

# ---------------------------------------------------------------------------
# 3bis) VALEURS D'EXEMPLE FICTIVES UTILISÉES DANS LES PROMPTS (anti-fuite)
# ---------------------------------------------------------------------------
# Toutes les valeurs "ex: ..." injectées ci-dessus (ENTITY_DESCRIPTIONS,
# SUPPLY_CHAIN_ENTITY_DESCRIPTIONS, exemples inline de PROMPT_ENGINEERED et
# PROMPT_TOPIC_SUPPLY_CHAIN) sont FICTIVES et ne doivent jamais apparaître
# dans une réponse du modèle. En pratique, remplacer un exemple "réaliste"
# par une valeur fictive (ex: CVE-0000-00000 au lieu d'un vrai CVE) ne suffit
# pas : le modèle recopie parfois l'exemple tel quel malgré la consigne.
# mistral_extractor._drop_template_leaks() filtre donc ces valeurs après
# coup, quelle que soit la valeur d'exemple choisie dans le prompt. Garder
# cet ensemble synchronisé avec les exemples ci-dessus si vous en ajoutez.
TEMPLATE_LEAK_VALUES = frozenset(
    {
        "0.0.0.0",
        "exemple-fictif.test",
        "hxxp://exemple-fictif.test",
        "hxxp://exemple-fictif.test/page",
        "cve-0000-00000",
        "cve-0000-000043",
        "cwe-000",
        "t0000.000",
        "libexemple-fictif",
    }
)

# ---------------------------------------------------------------------------
# 4) PARAMÈTRES MODÈLES
# ---------------------------------------------------------------------------
GLINER_MODEL_NAME = "urchade/gliner_multi-v2.1"  # modèle multilingue FR/EN

# Deux backends possibles pour Mistral 7B :
#  - "ollama"       -> le plus simple, nécessite `ollama pull mistral`
#  - "transformers" -> HuggingFace, nécessite un GPU avec assez de VRAM (>=16GB
#                       en fp16, ou usage de bitsandbytes en 4-bit)
MISTRAL_BACKEND = "ollama"
OLLAMA_MODEL_NAME = "mistral"  # nom du modèle dans ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TIMEOUT_SECONDS = 900  # 15 min : sur CPU, certains chunks longs dépassent
# largement 5 min -> évite un TimeoutError qui
# ferait planter tout le run en cours de route.
OLLAMA_MAX_RETRIES = 1  # nombre de nouvelles tentatives avant d'abandonner
# DÉFINITIVEMENT un chunk (au lieu de planter tout le script)
HF_MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.3"

GLINER_CONFIDENCE_THRESHOLD = 0.4  # seuil de score pour retenir une entité
