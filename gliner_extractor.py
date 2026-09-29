"""
gliner_extractor.py
--------------------
CAS 1 de l'expérience : extraction d'entités nommées avec GLiNER, un modèle
NER zero-shot (pas de prompt engineering, juste une liste de labels).

Sortie : JSON structuré { "entities": [ {text, label, start, end, score} ] }
"""

import json
import re

from gliner import GLiNER

from config import CYBER_ENTITY_LABELS, GLINER_MODEL_NAME, GLINER_CONFIDENCE_THRESHOLD
from pdf_extractor import is_glued_token

# GLiNER tronque silencieusement toute entrée au-delà de 384 tokens (son
# max_len) : "Sentence of length 636 has been truncated to 384". Les chunks
# de pdf_extractor.chunk_text (3000 caractères) font 540 à 640 tokens GLiNER
# sur Prompt-Injection.pdf — environ un tiers de chaque chunk n'était donc
# JAMAIS lu, et aucune entité de cette fin de chunk ne pouvait être trouvée.
# Chaque chunk est désormais découpé en fenêtres de WINDOW_WORDS mots (marge
# pour la ponctuation, que GLiNER compte comme tokens séparés), avec un
# chevauchement pour ne pas couper une entité à la frontière.
WINDOW_WORDS = 200
WINDOW_OVERLAP_WORDS = 30


class GLiNERExtractor:
    def __init__(self, model_name: str = GLINER_MODEL_NAME, labels: list[str] = None):
        """
        `labels` permet de comparer GLiNER sur une autre taxonomie que
        CYBER_ENTITY_LABELS (ex: SUPPLY_CHAIN_ENTITY_LABELS), pour une
        comparaison GLiNER vs Mistral équitable une fois le prompt "topic"
        activé côté MistralExtractor.
        """
        print(f"[GLiNER] Chargement du modèle {model_name} ...")
        self.model = GLiNER.from_pretrained(model_name)
        self.labels = labels or CYBER_ENTITY_LABELS

    @staticmethod
    def _windows(text: str) -> list[tuple[int, int]]:
        """(début, fin) en caractères de fenêtres de WINDOW_WORDS mots qui se chevauchent."""
        words = [m.span() for m in re.finditer(r"\S+", text)]
        if len(words) <= WINDOW_WORDS:
            return [(0, len(text))]
        step = WINDOW_WORDS - WINDOW_OVERLAP_WORDS
        spans = []
        for i in range(0, len(words), step):
            last = min(i + WINDOW_WORDS, len(words)) - 1
            spans.append((words[i][0], words[last][1]))
            if last == len(words) - 1:
                break
        return spans

    def _predict(self, text: str, threshold: float) -> list[dict]:
        """Prédiction fenêtre par fenêtre, offsets recalés sur `text`, doublons de chevauchement retirés."""
        seen, merged = set(), []
        for start, end in self._windows(text):
            for e in self.model.predict_entities(
                text[start:end], self.labels, threshold=threshold
            ):
                e = {**e, "start": e["start"] + start, "end": e["end"] + start}
                key = (e["start"], e["end"], e["label"])
                if key not in seen:
                    seen.add(key)
                    merged.append(e)
        return merged

    def extract(
        self, text: str, threshold: float = GLINER_CONFIDENCE_THRESHOLD
    ) -> dict:
        """Lance la prédiction NER et renvoie un dict prêt à sérialiser en JSON."""
        raw_entities = self._predict(text, threshold)

        entities = [
            {
                "text": e["text"],
                "label": e["label"],
                "start": e["start"],
                "end": e["end"],
                "score": round(float(e["score"]), 4),
            }
            for e in raw_entities
            # Rejette les mots soudés par une extraction PDF ratée
            # ("BingChatincentivizedustofollowthelinkbysaying"). Ils passaient
            # tous les contrôles existants : présents dans le texte source
            # (donc pas des hallucinations) et comptant pour un seul mot (donc
            # invisibles pour un filtre plafonnant un nombre de mots). Le vrai
            # correctif est en amont, dans extract_text_from_pdf ; ce filtre
            # est le garde-fou pour les PDF que la correction ne sauve pas
            # complètement.
            if not is_glued_token(e["text"])
        ]
        return {"method": "gliner_ner", "entities": entities}

    def extract_from_chunks(
        self,
        chunks: list[tuple[int, str]],
        threshold: float = GLINER_CONFIDENCE_THRESHOLD,
    ) -> dict:
        """
        Applique l'extraction sur plusieurs chunks et fusionne + dédoublonne.

        `chunks` est une liste de tuples (start_idx, chunk_text) telle que
        renvoyée par pdf_extractor.chunk_text. On utilise start_idx (position
        réelle du chunk dans le document original) pour recaler start/end de
        chaque entité sur le document ENTIER, plutôt que de les laisser
        relatifs au chunk local — sans ça, deux entités identiques dans des
        chunks différents auraient des offsets incohérents, et le dédoublonnage
        par (texte, label) restait correct mais start/end étaient inexploitables
        pour toute analyse de position dans le document.
        """
        all_entities = []
        seen = set()
        for start_idx, chunk in chunks:
            result = self.extract(chunk, threshold)
            for e in result["entities"]:
                e["start"] += start_idx
                e["end"] += start_idx
                key = (e["text"].lower(), e["label"])
                if key not in seen:
                    seen.add(key)
                    all_entities.append(e)
        return {"method": "gliner_ner", "entities": all_entities}


if __name__ == "__main__":
    sample_text = (
        "The APT group Lazarus exploited CVE-2023-23397 to compromise servers "
        "at 185.220.101.5 and deploy the malware Emotet. The email admin@corp.fr "
        "was used for phishing."
    )
    extractor = GLiNERExtractor()
    output = extractor.extract(sample_text)
    print(json.dumps(output, indent=2, ensure_ascii=False))
