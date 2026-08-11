"""
knowledge_table.py
--------------------
Step 5 du pipeline méthodologie/mitigation : la table de connaissance
elle-même. Un enregistrement par cas (attaque + éventuelle mitigation),
stocké en JSONL, avec les embeddings de attack_summary et mitigation_summary
calculés et stockés SÉPARÉMENT — le retrieval se fait sur la similarité de
l'attaque (Step 6, Tier 1), mais on veut pouvoir rechercher/inspecter les
mitigations indépendamment plus tard sans tout ré-embedder.

Construite à partir d'un VRAI corpus (viser 15-30+ papers couvrant plusieurs
catégories d'attaque) — un seul paper ne suffit pas à rendre le retrieval
(Step 6) significatif, cette table n'en est que le squelette.
"""

import requests

from config import KNOWLEDGE_TABLE_PATH, OLLAMA_EMBEDDING_MODEL, OLLAMA_EMBEDDINGS_URL
from generalizability import score_generalizability
from jsonl_utils import append_jsonl, read_jsonl


class EmbeddingError(Exception):
    """Levée quand Ollama échoue à produire un embedding (modèle non installé, timeout...)."""


def embed_text(text: str, timeout: int = 60) -> list[float]:
    """
    Calcule l'embedding d'un texte via Ollama (`ollama pull nomic-embed-text`
    au préalable). Choisi pour rester sur l'infrastructure déjà en place
    plutôt que d'ajouter sentence-transformers + un second téléchargement
    PyTorch juste pour l'embedding.
    """
    try:
        response = requests.post(
            OLLAMA_EMBEDDINGS_URL,
            json={"model": OLLAMA_EMBEDDING_MODEL, "prompt": text},
            timeout=timeout,
        )
        response.raise_for_status()
        embedding = response.json().get("embedding")
        if not embedding:
            raise EmbeddingError(
                f"Réponse Ollama sans champ 'embedding' exploitable : {response.text[:200]}"
            )
        return embedding
    except requests.exceptions.RequestException as e:
        raise EmbeddingError(f"Échec de l'appel à Ollama pour l'embedding : {e}") from e


def build_record(
    methodology_record: dict,
    generalizability_score: float | None,
    source_paper: str,
) -> dict:
    """
    Construit UN enregistrement de la table de connaissance à partir de la
    sortie de MethodologyExtractor.extract() (Steps 1-3, déjà validée) et du
    score de généralisabilité (Step 4). mitigation_embedding reste None si
    mitigation_summary est None (honest null — pas d'embedding inventé pour
    du texte qui n'existe pas).
    """
    attack_summary = methodology_record.get("attack_summary")
    mitigation_summary = methodology_record.get("mitigation_summary")

    attack_embedding = embed_text(attack_summary) if attack_summary else None
    mitigation_embedding = (
        embed_text(mitigation_summary) if mitigation_summary else None
    )

    return {
        "attack_summary": attack_summary,
        "attack_embedding": attack_embedding,
        "category": methodology_record.get("mitre_technique_id"),
        "category_name": methodology_record.get("mitre_technique_name"),
        "mitigation_summary": mitigation_summary,
        "mitigation_embedding": mitigation_embedding,
        "generalizability_score": generalizability_score,
        "source_paper": source_paper,
        "confidence": methodology_record.get("confidence"),
    }


def add_record(record: dict, table_path: str = KNOWLEDGE_TABLE_PATH) -> None:
    """Ajoute UN enregistrement déjà construit (build_record) à la table."""
    append_jsonl(table_path, record)


def load_table(table_path: str = KNOWLEDGE_TABLE_PATH) -> list[dict]:
    """Charge tous les enregistrements de la table de connaissance."""
    return read_jsonl(table_path)


def build_table_from_methodology_records(
    methodology_records: list[dict],
    layer1_entities_per_chunk: list[list[dict]],
    source_paper: str,
    table_path: str = KNOWLEDGE_TABLE_PATH,
) -> list[dict]:
    """
    Construit et sauvegarde un enregistrement par chunk où une attaque a été
    confirmée (attack_present). Les chunks sans attaque ne produisent pas de
    ligne — ce n'est pas un cas à retrouver par similarité plus tard. Renvoie
    la liste des enregistrements ajoutés, pour l'inspection manuelle
    recommandée (Step 1 : valider à la main les résumés des 3 case studies
    avant de passer à la suite).
    """
    if len(methodology_records) != len(layer1_entities_per_chunk):
        raise ValueError(
            f"methodology_records ({len(methodology_records)}) et "
            f"layer1_entities_per_chunk ({len(layer1_entities_per_chunk)}) "
            f"doivent avoir la même longueur"
        )
    added = []
    for record, entities in zip(methodology_records, layer1_entities_per_chunk):
        if not record.get("attack_present"):
            continue
        score = score_generalizability(record.get("mitigation_summary"), entities)
        kt_record = build_record(record, score, source_paper)
        add_record(kt_record, table_path)
        added.append(kt_record)
    return added
