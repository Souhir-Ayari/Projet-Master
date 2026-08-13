"""
vector_store.py
-----------------
Stockage des embeddings de la table de connaissance EN DEHORS du JSONL
(knowledge_table.py), dans un fichier .npz numpy compact plutôt qu'inline
dans chaque enregistrement JSON.

Pourquoi : chaque embedding fait ~1600 floats (~40 Ko en JSON, bien plus
verbeux qu'en binaire). Avec 15-30 papers x plusieurs chunks, garder les
vecteurs inline ferait grossir le JSONL à plusieurs dizaines de Mo, et
query_knowledge.py devrait tout charger + désérialiser du JSON à chaque appel
juste pour faire une recherche par similarité. Un .npz numpy se charge une
fois, et le calcul de similarité cosinus devient une opération matricielle
vectorisée au lieu d'une boucle Python par enregistrement — accessoirement
bien plus rapide, pas seulement plus compact.

knowledge_table.jsonl garde le TEXTE et les métadonnées (attack_summary,
category, mitigation_summary, generalizability_score, source_paper,
confidence, record_id) ; ce module associe record_id -> vecteur.
"""

import os

import numpy as np


def _load_store(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Renvoie (ids, matrice NxD). Vides si le fichier n'existe pas encore."""
    if not os.path.exists(path):
        return np.array([], dtype="<U64"), np.zeros((0, 0), dtype=np.float32)
    data = np.load(path, allow_pickle=False)
    return data["ids"], data["vectors"]


def add_vectors(path: str, new_ids: list[str], new_vectors: list[list[float]]) -> None:
    """
    Ajoute des vecteurs au store, en le créant si besoin. Append par
    recharge-concatène-réécrit : suffisant tant que le corpus reste de
    l'ordre de quelques milliers d'enregistrements (le cas visé, 15-30
    papers) — un vrai index incrémental (FAISS) ne se justifie qu'au-delà.
    """
    if not new_ids:
        return
    ids, vectors = _load_store(path)
    new_vectors_arr = np.array(new_vectors, dtype=np.float32)
    vectors = (
        new_vectors_arr if vectors.size == 0 else np.vstack([vectors, new_vectors_arr])
    )
    ids = np.concatenate([ids, np.array(new_ids, dtype="<U64")])

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    np.savez_compressed(path, ids=ids, vectors=vectors)


def load_vectors(path: str) -> tuple[list[str], np.ndarray]:
    """Renvoie (liste d'ids, matrice NxD) — matrice vide si le fichier n'existe pas encore."""
    ids, vectors = _load_store(path)
    return list(ids), vectors


def cosine_similarities(query_vector: list[float], matrix: np.ndarray) -> np.ndarray:
    """
    Similarité cosinus vectorisée entre UN vecteur requête et TOUTES les
    lignes de `matrix` en une seule opération numpy, plutôt qu'une boucle
    Python par enregistrement (ce que faisait retrieval.tier1_retrieve avant
    ce fix).
    """
    if matrix.size == 0:
        return np.array([])
    query = np.asarray(query_vector, dtype=np.float32)
    query_norm = np.linalg.norm(query)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    denom = query_norm * matrix_norms
    denom[denom == 0] = 1e-10  # évite une division par zéro pour un vecteur nul
    return (matrix @ query) / denom


if __name__ == "__main__":
    import tempfile

    tmp = tempfile.mktemp(suffix=".npz")
    add_vectors(tmp, ["a", "b"], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    add_vectors(tmp, ["c"], [[1.0, 0.0, 0.0]])  # identique à "a"

    ids, matrix = load_vectors(tmp)
    print("ids:", ids)
    print("matrice:", matrix.shape)

    sims = cosine_similarities([1.0, 0.0, 0.0], matrix)
    for record_id, sim in zip(ids, sims):
        print(f"  {record_id} -> {sim:.4f}")

    os.remove(tmp)
