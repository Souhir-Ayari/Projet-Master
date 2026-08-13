"""
knowledge_table.py
--------------------
Step 5 du pipeline méthodologie/mitigation : la table de connaissance
elle-même. Un enregistrement par cas (attaque + éventuelle mitigation),
stocké en JSONL — le TEXTE et les métadonnées uniquement, les embeddings
étant stockés à part dans des fichiers .npz (voir vector_store.py) plutôt
qu'inline dans chaque enregistrement JSON, pour que le JSONL reste
compact et rapide à parcourir même quand le corpus grandit.

attack_embedding et mitigation_embedding sont calculés et stockés
SÉPARÉMENT — le retrieval se fait sur la similarité de l'attaque (Step 6,
Tier 1), mais on veut pouvoir rechercher/inspecter les mitigations
indépendamment plus tard sans tout ré-embedder.

Construite à partir d'un VRAI corpus (viser 15-30+ papers couvrant plusieurs
catégories d'attaque) — un seul paper ne suffit pas à rendre le retrieval
(Step 6) significatif, cette table n'en est que le squelette.
"""

import uuid

import requests

from config import (
    KNOWLEDGE_ATTACK_VECTORS_PATH,
    KNOWLEDGE_MITIGATION_VECTORS_PATH,
    KNOWLEDGE_TABLE_PATH,
    OLLAMA_EMBEDDING_MODEL,
    OLLAMA_EMBEDDINGS_URL,
)
from generalizability import score_generalizability
from jsonl_utils import append_jsonl, read_jsonl
from vector_store import add_vectors


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
    score de généralisabilité (Step 4). Un "record_id" unique (uuid4) est
    généré ici, utilisé ensuite pour associer les embeddings dans
    vector_store.py sans les porter dans ce dict.

    Renvoie (record, attack_embedding, mitigation_embedding) : les deux
    derniers ne sont PAS inclus dans `record` (voir add_record), mais
    calculés ici pour n'appeler Ollama qu'une fois par texte.
    mitigation_embedding est None si mitigation_summary est None (honest
    null — pas d'embedding inventé pour du texte qui n'existe pas).
    """
    attack_summary = methodology_record.get("attack_summary")
    mitigation_summary = methodology_record.get("mitigation_summary")

    attack_embedding = embed_text(attack_summary) if attack_summary else None
    mitigation_embedding = (
        embed_text(mitigation_summary) if mitigation_summary else None
    )

    record = {
        "record_id": uuid.uuid4().hex,
        "attack_summary": attack_summary,
        "category": methodology_record.get("mitre_technique_id"),
        "category_name": methodology_record.get("mitre_technique_name"),
        "mitigation_summary": mitigation_summary,
        "generalizability_score": generalizability_score,
        "source_paper": source_paper,
        "confidence": methodology_record.get("confidence"),
    }
    return record, attack_embedding, mitigation_embedding


def add_record(
    record: dict,
    attack_embedding: list[float] | None,
    mitigation_embedding: list[float] | None,
    table_path: str = KNOWLEDGE_TABLE_PATH,
    attack_vectors_path: str = KNOWLEDGE_ATTACK_VECTORS_PATH,
    mitigation_vectors_path: str = KNOWLEDGE_MITIGATION_VECTORS_PATH,
) -> None:
    """
    Ajoute UN enregistrement déjà construit (build_record) : les métadonnées
    dans le JSONL, les embeddings dans les stores vectoriels séparés, reliés
    par record["record_id"].
    """
    append_jsonl(table_path, record)
    if attack_embedding is not None:
        add_vectors(attack_vectors_path, [record["record_id"]], [attack_embedding])
    if mitigation_embedding is not None:
        add_vectors(
            mitigation_vectors_path, [record["record_id"]], [mitigation_embedding]
        )


def load_table(table_path: str = KNOWLEDGE_TABLE_PATH) -> list[dict]:
    """Charge tous les enregistrements (métadonnées seulement, pas les embeddings)."""
    return read_jsonl(table_path)


def build_table_from_methodology_records(
    methodology_records: list[dict],
    layer1_entities_per_chunk: list[list[dict]],
    source_paper: str,
    table_path: str = KNOWLEDGE_TABLE_PATH,
    attack_vectors_path: str = KNOWLEDGE_ATTACK_VECTORS_PATH,
    mitigation_vectors_path: str = KNOWLEDGE_MITIGATION_VECTORS_PATH,
) -> list[dict]:
    """
    Construit et sauvegarde un enregistrement par chunk où une attaque a été
    confirmée (attack_present). Les chunks sans attaque ne produisent pas de
    ligne — ce n'est pas un cas à retrouver par similarité plus tard. Renvoie
    la liste des enregistrements ajoutés (métadonnées seulement), pour
    l'inspection manuelle recommandée (Step 1 : valider à la main les
    résumés des 3 case studies avant de passer à la suite).

    attack_vectors_path/mitigation_vectors_path sont explicitement
    transmis à add_record() plutôt que de laisser ses valeurs par défaut
    s'appliquer : sinon, un table_path personnalisé (ex: --table sur
    build_knowledge.py) désynchronise le JSONL (au bon endroit) des
    vecteurs (qui atterriraient quand même sur les chemins par défaut de
    config.py).
    """
    if len(methodology_records) != len(layer1_entities_per_chunk):
        raise ValueError(
            f"methodology_records ({len(methodology_records)}) et "
            f"layer1_entities_per_chunk ({len(layer1_entities_per_chunk)}) "
            f"doivent avoir la même longueur"
        )
    added = []
    for mrecord, entities in zip(methodology_records, layer1_entities_per_chunk):
        if not mrecord.get("attack_present"):
            continue
        score = score_generalizability(mrecord.get("mitigation_summary"), entities)
        kt_record, attack_embedding, mitigation_embedding = build_record(
            mrecord, score, source_paper
        )
        add_record(
            kt_record,
            attack_embedding,
            mitigation_embedding,
            table_path,
            attack_vectors_path,
            mitigation_vectors_path,
        )
        added.append(kt_record)
    return added
