"""
jsonl_utils.py
---------------
Petits utilitaires JSONL partagés par methodology_extractor.py (Step 1,
sauvegarde immédiate des résumés bruts avant tout traitement en aval) et
knowledge_table.py (Step 5, la table de connaissance elle-même).

Écriture en append immédiat, une ligne = un enregistrement : si le run est
interrompu en cours de route, tout ce qui a déjà été généré reste inspectable
et exploitable, plutôt que perdu dans une structure en mémoire jamais
sauvegardée.
"""

import json
import os


def append_jsonl(path: str, record: dict) -> None:
    """Ajoute UN enregistrement à la fin du fichier, créant le dossier si besoin."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: str) -> list[dict]:
    """Lit tous les enregistrements d'un fichier JSONL. Renvoie [] si le fichier n'existe pas encore."""
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(path: str, records: list[dict]) -> None:
    """
    Écrit une liste d'enregistrements en REMPLAÇANT le contenu existant
    (contrairement à append_jsonl). Utilisé pour réécrire un fichier après
    filtrage — ex: knowledge_table.replace_paper_records() retire les
    anciens enregistrements d'un paper avant d'en ajouter de nouveaux.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def clear_jsonl(path: str) -> None:
    """
    Supprime un fichier JSONL s'il existe — pour repartir propre en tête
    d'un nouveau run plutôt que d'empiler les résultats de runs précédents
    (ex: methodology_<pdf>.jsonl, un fichier par paper : le ré-exécuter sur
    le même PDF doit remplacer, pas empiler, vu que le LLM n'est pas
    déterministe et produit des variantes légèrement différentes à chaque
    run plutôt que des doublons exacts faciles à filtrer après coup).
    """
    if os.path.exists(path):
        os.remove(path)
