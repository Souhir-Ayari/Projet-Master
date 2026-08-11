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


if __name__ == "__main__":
    techs = load_techniques()
    print(f"{len(techs)} techniques chargées.")
    sample_valid = next(iter(techs))
    print(f"Exemple valide : {sample_valid} -> {technique_name(sample_valid, techs)}")
    print(f"ID inventé 'T9999.999' valide ? {is_valid_technique_id('T9999.999', techs)}")
