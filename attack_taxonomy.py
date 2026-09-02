"""
attack_taxonomy.py
-------------------
Step 2 du pipeline méthodologie/mitigation : ancrage sur une VRAIE taxonomie
publique plutôt qu'une catégorie inventée par le LLM — référentiel citable,
important pour la crédibilité d'un papier.

Deux domaines sont supportés, chacun avec son référentiel officiel :

  - "llm"          -> MITRE ATLAS (Adversarial Threat Landscape for AI
                      Systems) : injection de prompt, jailbreak, fuite de
                      données, empoisonnement RAG... C'est le référentiel
                      pertinent pour le sujet "Nexus Intel" (menaces sur les
                      LLM), et le domaine par DÉFAUT.
  - "supply_chain" -> MITRE ATT&CK (Enterprise) : compromission de chaîne
                      d'approvisionnement logicielle (XZ Utils, SolarWinds,
                      Log4Shell). Conservé pour que les résultats déjà
                      produits sur ce corpus restent reproductibles.

Les deux bundles STIX ont la même structure (objets "attack-pattern" avec
une external_reference portant l'identifiant officiel), seuls changent
l'URL, le nom de source et le format d'identifiant (Txxxx vs AML.Txxxx) —
d'où le registre _TAXONOMIES ci-dessous plutôt que deux modules séparés.

Le LLM PROPOSE un identifiant de technique (voir config.PROMPT_METHODOLOGY,
champ "mitre_technique_id") ; ce module VALIDE contre la liste réelle, sur le
même principe que mistral_extractor._filter_valid_labels : rejeter plutôt que
faire confiance au modèle.
"""

import json
import os
import re

import requests

# Les constantes de domaine sont définies dans config.py (source de vérité
# unique) et ré-exportées ici pour que `attack_taxonomy.DOMAIN_LLM` reste
# utilisable depuis les modules qui raisonnent en termes de taxonomie.
from config import (
    DEFAULT_DOMAIN,
    DOMAIN_LLM,
    DOMAIN_SUPPLY_CHAIN,
    MITRE_ATLAS_CACHE_PATH,
    MITRE_ATLAS_STIX_URL,
    MITRE_ATTACK_CACHE_PATH,
    MITRE_ATTACK_STIX_URL,
)

# ---------------------------------------------------------------------------
# Short-lists de techniques pertinentes, par domaine
# ---------------------------------------------------------------------------
# Constaté en conditions réelles : en laissant le modèle choisir librement
# parmi les centaines de techniques d'un référentiel complet, il propose des
# ID RÉELS mais SANS RAPPORT avec l'attaque décrite (ex: "T1078.001 Valid
# Accounts: Default Accounts" assigné à l'exploitation de Log4Shell) — une
# simple vérification d'existence les laisse passer. Même remède que pour la
# sur-extraction Layer 1 : réduire l'espace de choix à ce qui est
# effectivement pertinent pour le domaine.

# MITRE ATLAS — menaces sur les LLM/systèmes d'IA. Tous ces ID sont vérifiés
# présents dans le bundle ATLAS réel (voir data/mitre_atlas_techniques.json).
# AML.T0051.001 (Indirect) correspond précisément à l'attaque de Greshake et
# al. citée en référence [2] du sujet ; AML.T0054 (Jailbreak) couvre les
# travaux type LG-SCO.
LLM_THREAT_TECHNIQUE_IDS = frozenset(
    {
        # --- Injection de prompt (coeur du sujet) ---
        "AML.T0051",  # LLM Prompt Injection
        "AML.T0051.000",  # Direct
        "AML.T0051.001",  # Indirect
        "AML.T0051.002",  # Triggered
        "AML.T0093",  # Prompt Infiltration via Public-Facing Application
        "AML.T0094",  # Delay Execution of LLM Instructions
        "AML.T0061",  # LLM Prompt Self-Replication
        # --- Contournement des garde-fous ---
        "AML.T0054",  # LLM Jailbreak
        "AML.T0065",  # LLM Prompt Crafting
        "AML.T0068",  # LLM Prompt Obfuscation
        "AML.T0015",  # Evade AI Model
        # --- Extraction / fuite ---
        "AML.T0056",  # Extract LLM System Prompt
        "AML.T0057",  # LLM Data Leakage
        "AML.T0069",  # Discover LLM System Information
        "AML.T0069.002",  # System Prompt
        "AML.T0024.000",  # Infer Training Data Membership
        # --- Manipulation du contexte / RAG / agents ---
        "AML.T0070",  # RAG Poisoning
        "AML.T0071",  # False RAG Entry Injection
        "AML.T0080",  # AI Agent Context Poisoning
        "AML.T0092",  # Manipulate User LLM Chat History
        "AML.T0067",  # LLM Trusted Output Components Manipulation
        "AML.T0086",  # Exfiltration via AI Agent Tool Invocation
        "AML.T0110",  # AI Agent Tool Poisoning
        # --- Empoisonnement en amont ---
        "AML.T0020",  # Poison Training Data
    }
)

# MITRE ATT&CK — compromission de chaîne d'approvisionnement logicielle.
SUPPLY_CHAIN_TECHNIQUE_IDS = frozenset(
    {
        "T1195",  # Supply Chain Compromise
        "T1195.001",  # Compromise Software Dependencies and Development Tools
        "T1195.002",  # Compromise Software Supply Chain
        "T1195.003",  # Compromise Hardware Supply Chain
        "T1199",  # Trusted Relationship — mainteneur qui gagne la confiance au fil du temps
        "T1078",  # Valid Accounts (générique : compte mainteneur compromis, une fois obtenu)
        "T1566",  # Phishing
        "T1566.001",  # Spearphishing Attachment
        "T1566.002",  # Spearphishing Link
        "T1554",  # Compromise Host Software Binary
        "T1553",  # Subvert Trust Controls
        "T1553.002",  # Code Signing — mises à jour signées mais malveillantes (type SolarWinds)
        "T1553.004",  # Install Root Certificate
        "T1190",  # Exploit Public-Facing Application — cas type Log4Shell : exploitation
        # d'une vulnérabilité dans une dépendance déjà déployée, PAS une insertion dans
        # la chaîne d'approvisionnement elle-même. Distinction volontaire : forcer
        # Log4Shell dans une sous-technique "Valid Accounts"/"Trusted Relationship"
        # serait aussi faux que ce que ce filtre est censé corriger.
    }
)

_TAXONOMIES = {
    DOMAIN_LLM: {
        "label": "MITRE ATLAS",
        "url": MITRE_ATLAS_STIX_URL,
        "cache_path": MITRE_ATLAS_CACHE_PATH,
        "source_name": "mitre-atlas",
        "id_regex": re.compile(r"^AML\.T\d{4}(\.\d{3})?$", re.IGNORECASE),
        "shortlist": LLM_THREAT_TECHNIQUE_IDS,
    },
    DOMAIN_SUPPLY_CHAIN: {
        "label": "MITRE ATT&CK (Enterprise)",
        "url": MITRE_ATTACK_STIX_URL,
        "cache_path": MITRE_ATTACK_CACHE_PATH,
        "source_name": "mitre-attack",
        "id_regex": re.compile(r"^T\d{4}(\.\d{3})?$", re.IGNORECASE),
        "shortlist": SUPPLY_CHAIN_TECHNIQUE_IDS,
    },
}


def available_domains() -> list[str]:
    """Domaines supportés, pour les valeurs de --domain en ligne de commande."""
    return sorted(_TAXONOMIES)


def _taxonomy(domain: str) -> dict:
    try:
        return _TAXONOMIES[domain]
    except KeyError:
        raise ValueError(
            f"Domaine inconnu : {domain!r}. Domaines supportés : "
            f"{', '.join(available_domains())}"
        ) from None


def taxonomy_label(domain: str = DEFAULT_DOMAIN) -> str:
    """Nom lisible du référentiel du domaine ("MITRE ATLAS", "MITRE ATT&CK (Enterprise)")."""
    return _taxonomy(domain)["label"]


def _download_and_cache(domain: str = DEFAULT_DOMAIN, timeout: int = 120) -> dict:
    """
    Télécharge le bundle STIX du référentiel du domaine et n'en garde que ce
    qui est utile ici : {technique_id: technique_name} pour chaque
    "attack-pattern" non révoqué/déprécié. Les bundles complets contiennent
    aussi les groupes, mitigations et relations (~50 Mo pour ATT&CK) — on ne
    persiste localement que l'extrait dont ce module a besoin.
    """
    taxo = _taxonomy(domain)
    print(f"[{taxo['label']}] Téléchargement du référentiel depuis {taxo['url']} ...")
    response = requests.get(taxo["url"], timeout=timeout)
    response.raise_for_status()
    bundle = response.json()

    techniques = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        technique_id = None
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == taxo["source_name"]:
                technique_id = ref.get("external_id")
                break
        if technique_id and taxo["id_regex"].match(technique_id):
            techniques[technique_id.upper()] = obj.get("name", "")

    cache_path = taxo["cache_path"]
    directory = os.path.dirname(cache_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(techniques, f, ensure_ascii=False, indent=2)
    print(f"[{taxo['label']}] {len(techniques)} techniques mises en cache -> {cache_path}")
    return techniques


def load_techniques(domain: str = DEFAULT_DOMAIN, refresh: bool = False) -> dict:
    """
    Charge {technique_id: technique_name} depuis le cache local du domaine,
    en le (re)téléchargeant si absent ou si refresh=True.

    Si le téléchargement échoue : retombe sur le cache local s'il existe déjà
    (avec avertissement) ; lève une erreur explicite seulement s'il n'y a NI
    cache NI téléchargement possible — mieux vaut un échec net qu'une
    validation qui accepterait silencieusement n'importe quel ID faute de
    référentiel chargé.
    """
    taxo = _taxonomy(domain)
    cache_path = taxo["cache_path"]
    if refresh or not os.path.exists(cache_path):
        try:
            return _download_and_cache(domain)
        except requests.exceptions.RequestException as e:
            if os.path.exists(cache_path):
                print(
                    f"[⚠] Échec du téléchargement {taxo['label']} ({e}), "
                    f"utilisation du cache existant."
                )
            else:
                raise RuntimeError(
                    f"Impossible de télécharger le référentiel {taxo['label']} "
                    f"et aucun cache local trouvé ({cache_path}). Vérifiez la "
                    f"connexion réseau, ou lancez "
                    f"load_techniques({domain!r}, refresh=True) une fois la "
                    f"connexion rétablie."
                ) from e
    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_valid_technique_id(
    technique_id: str | None, techniques: dict = None, domain: str = DEFAULT_DOMAIN
) -> bool:
    """Vérifie qu'un identifiant proposé par le LLM existe réellement dans le référentiel."""
    if not technique_id:
        return False
    techniques = techniques if techniques is not None else load_techniques(domain)
    return technique_id.strip().upper() in techniques


def technique_name(
    technique_id: str | None, techniques: dict = None, domain: str = DEFAULT_DOMAIN
) -> str | None:
    """
    Nom officiel de la technique, ou None si l'ID est invalide/absent. Les
    sous-techniques sont qualifiées par leur parente ("LLM Prompt Injection:
    Indirect" plutôt que "Indirect" tout court) : c'est ce nom qui est stocké
    dans la table de connaissance et lu par un humain, où "Indirect" seul
    n'aurait aucun sens.
    """
    if not technique_id:
        return None
    techniques = techniques if techniques is not None else load_techniques(domain)
    technique_id = technique_id.strip().upper()
    if technique_id not in techniques:
        return None
    return _display_name(technique_id, techniques)


def is_in_shortlist(technique_id: str | None, domain: str = DEFAULT_DOMAIN) -> bool:
    """
    Vérifie qu'un identifiant proposé par le LLM fait partie de la short-list
    pertinente pour CE domaine. Plus strict que is_valid_technique_id() : un
    ID réel mais hors-sujet (ex: T1078.001 proposé pour Log4Shell) est rejeté
    ici, alors qu'il passerait la simple vérification d'existence.
    """
    if not technique_id:
        return False
    return technique_id.strip().upper() in _taxonomy(domain)["shortlist"]


def _display_name(technique_id: str, techniques: dict) -> str:
    """
    Nom lisible d'une technique, préfixé du nom de sa technique parente quand
    c'est une sous-technique. Dans les bundles STIX, une sous-technique ne
    porte que son nom court — "Direct", "Indirect", "System Prompt" pour
    AML.T0051.000/.001 et AML.T0069.002. Injectés seuls dans le prompt, ces
    noms ne veulent rien dire ("Indirect" quoi ?) et le modèle ne peut pas
    choisir correctement ; MITRE les affiche toujours "Parent: Enfant".
    """
    name = techniques.get(technique_id, "")
    # Une sous-technique se termine par ".NNN" : "T1195.001" -> "T1195",
    # "AML.T0051.001" -> "AML.T0051". Le point de "AML." ne compte pas.
    head, _, tail = technique_id.rpartition(".")
    parent_id = head if head and tail.isdigit() and len(tail) == 3 else ""
    parent_name = techniques.get(parent_id, "") if parent_id else ""
    if parent_name and name:
        return f"{parent_name}: {name}"
    return name


def shortlist_labels_block(domain: str = DEFAULT_DOMAIN, techniques: dict = None) -> str:
    """
    Construit le bloc "ID : nom" injecté dans PROMPT_METHODOLOGY, pour que le
    modèle choisisse dans une liste fermée de techniques plausibles au lieu
    d'inventer un ID parmi les centaines du référentiel complet.
    """
    techniques = techniques if techniques is not None else load_techniques(domain)
    lines = []
    for technique_id in sorted(_taxonomy(domain)["shortlist"]):
        name = _display_name(technique_id, techniques)
        lines.append(f"- {technique_id} : {name}" if name else f"- {technique_id}")
    return "\n".join(lines)


def id_prefix_pattern(domain: str = DEFAULT_DOMAIN) -> re.Pattern:
    """
    Regex de normalisation d'un ID proposé par le modèle : il ajoute parfois
    le nom de la technique après l'identifiant ("AML.T0051.001: Indirect"),
    ce qui fait échouer une comparaison stricte alors que l'ID lui-même est
    correct. Utilisée par methodology_extractor._normalize_technique_id.
    """
    pattern = _taxonomy(domain)["id_regex"].pattern
    return re.compile("^(" + pattern.lstrip("^").rstrip("$") + ")", re.IGNORECASE)


if __name__ == "__main__":
    for domain in available_domains():
        taxo = _taxonomy(domain)
        print(f"\n=== domaine {domain!r} — {taxo['label']} ===")
        techs = load_techniques(domain)
        print(f"{len(techs)} techniques chargées au total.")
        print(f"Short-list ({len(taxo['shortlist'])} techniques) injectée dans le prompt :")
        print(shortlist_labels_block(domain, techs))
