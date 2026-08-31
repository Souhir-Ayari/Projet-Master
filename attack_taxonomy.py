"""
attack_taxonomy.py
-------------------
Step 2 du pipeline méthodologie/mitigation : ancrage sur la vraie taxonomie
MITRE ATT&CK plutôt qu'une catégorie inventée par le LLM. Remplace un système
de labels ad hoc par un référentiel citable — important pour la crédibilité
d'un papier (ICAART).

Le LLM PROPOSE un identifiant de technique (voir config.PROMPT_METHODOLOGY,
champ "mitre_technique_id") ; ce module VALIDE contre la liste réelle, sur le
même principe que mistral_extractor._filter_valid_labels : rejeter plutôt que
faire confiance au modèle.
"""

import json
import os
import re

import requests

from config import MITRE_STIX_URL, MITRE_CACHE_PATH

_TECHNIQUE_ID_RE = re.compile(r"^T\d{4}(\.\d{3})?$", re.IGNORECASE)

# Short-list de techniques MITRE ATT&CK pertinentes pour les attaques de
# chaîne d'approvisionnement logicielle. Constaté en conditions réelles : en
# laissant le modèle choisir librement parmi les ~700 techniques du
# référentiel complet, il propose des ID RÉELS mais SANS RAPPORT avec
# l'attaque décrite (ex: "T1078.001 Valid Accounts: Default Accounts" assigné
# à l'exploitation de Log4Shell, "T1566.001 Spearphishing Attachment" assigné
# à la compromission du build SolarWinds) — is_valid_technique_id() les
# laissait passer car ils EXISTENT, même s'ils sont faux pour ce cas précis.
# Même remède que pour la sur-extraction Layer 1 (CYBER_ENTITY_LABELS trop
# large sur ce document) : réduire l'espace de choix à ce qui est
# effectivement pertinent, plutôt que faire confiance à un tri libre parmi
# des centaines d'options. Tous les ID ci-dessous sont vérifiés présents
# dans le référentiel MITRE ATT&CK réel (voir data/mitre_attack_techniques.json).
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


def _download_and_cache(cache_path: str = MITRE_CACHE_PATH, timeout: int = 120) -> dict:
    """
    Télécharge le bundle STIX MITRE ATT&CK (Enterprise, ~50 Mo) et n'en garde
    que ce qui est utile ici : {technique_id: technique_name} pour chaque
    "attack-pattern" non révoqué/déprécié. Le bundle complet contient aussi
    les groupes, logiciels, mitigations et relations — on ne persiste
    localement que l'extrait dont ce module a besoin, pour ne pas garder 50 Mo
    dans le dépôt à chaque run.
    """
    print(f"[MITRE ATT&CK] Téléchargement du référentiel depuis {MITRE_STIX_URL} ...")
    response = requests.get(MITRE_STIX_URL, timeout=timeout)
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
            if ref.get("source_name") == "mitre-attack":
                technique_id = ref.get("external_id")
                break
        if technique_id and _TECHNIQUE_ID_RE.match(technique_id):
            techniques[technique_id.upper()] = obj.get("name", "")

    directory = os.path.dirname(cache_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(techniques, f, ensure_ascii=False, indent=2)
    print(f"[MITRE ATT&CK] {len(techniques)} techniques mises en cache -> {cache_path}")
    return techniques


def load_techniques(cache_path: str = MITRE_CACHE_PATH, refresh: bool = False) -> dict:
    """
    Charge {technique_id: technique_name} depuis le cache local, en le
    (re)téléchargeant si absent ou si refresh=True.

    Si le téléchargement échoue : retombe sur le cache local s'il existe déjà
    (avec avertissement) ; lève une erreur explicite seulement s'il n'y a NI
    cache NI téléchargement possible — mieux vaut un échec net qu'une
    validation qui accepterait silencieusement n'importe quel ID faute de
    référentiel chargé.
    """
    if refresh or not os.path.exists(cache_path):
        try:
            return _download_and_cache(cache_path)
        except requests.exceptions.RequestException as e:
            if os.path.exists(cache_path):
                print(
                    f"[⚠] Échec du téléchargement MITRE ATT&CK ({e}), "
                    f"utilisation du cache existant."
                )
            else:
                raise RuntimeError(
                    f"Impossible de télécharger le référentiel MITRE ATT&CK et "
                    f"aucun cache local trouvé ({cache_path}). Vérifiez la "
                    f"connexion réseau, ou lancez load_techniques(refresh=True) "
                    f"une fois la connexion rétablie."
                ) from e
    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_valid_technique_id(technique_id: str | None, techniques: dict = None) -> bool:
    """Vérifie qu'un identifiant proposé par le LLM existe réellement dans MITRE ATT&CK."""
    if not technique_id:
        return False
    techniques = techniques if techniques is not None else load_techniques()
    return technique_id.strip().upper() in techniques


def technique_name(technique_id: str | None, techniques: dict = None) -> str | None:
    """Nom officiel de la technique, ou None si l'ID est invalide/absent."""
    if not technique_id:
        return None
    techniques = techniques if techniques is not None else load_techniques()
    return techniques.get(technique_id.strip().upper())


def is_valid_supply_chain_technique_id(technique_id: str | None) -> bool:
    """
    Vérifie qu'un identifiant proposé par le LLM est à la fois un VRAI ID
    MITRE ATT&CK ET fait partie de la short-list pertinente pour les attaques
    de chaîne d'approvisionnement (SUPPLY_CHAIN_TECHNIQUE_IDS ci-dessus).
    Plus strict que is_valid_technique_id() : un ID réel mais hors-sujet
    (ex: T1078.001 proposé pour Log4Shell) est rejeté ici, alors qu'il
    passerait la simple vérification d'existence.
    """
    if not technique_id:
        return False
    return technique_id.strip().upper() in SUPPLY_CHAIN_TECHNIQUE_IDS


def supply_chain_labels_block(techniques: dict = None) -> str:
    """
    Construit le bloc "ID : nom" injecté dans PROMPT_METHODOLOGY, pour que le
    modèle choisisse dans une liste fermée de techniques plausibles au lieu
    d'inventer un ID parmi les ~700 du référentiel complet.
    """
    techniques = techniques if techniques is not None else load_techniques()
    lines = []
    for technique_id in sorted(SUPPLY_CHAIN_TECHNIQUE_IDS):
        name = techniques.get(technique_id, "")
        lines.append(f"- {technique_id} : {name}" if name else f"- {technique_id}")
    return "\n".join(lines)


if __name__ == "__main__":
    techs = load_techniques()
    print(f"{len(techs)} techniques chargées.")
    sample_valid = next(iter(techs))
    print(f"Exemple valide : {sample_valid} -> {technique_name(sample_valid, techs)}")
    print(f"ID inventé 'T9999.999' valide ? {is_valid_technique_id('T9999.999', techs)}")
    print(
        f"ID réel mais hors sujet 'T1078.001' valide pour la short-list "
        f"supply chain ? {is_valid_supply_chain_technique_id('T1078.001')}"
    )
    print(f"'T1195' (Supply Chain Compromise) valide pour la short-list ? "
          f"{is_valid_supply_chain_technique_id('T1195')}")
    print("\nShort-list injectée dans le prompt :")
    print(supply_chain_labels_block(techs))
