"""
gliner_extractor.py
--------------------
CAS 1 de l'expérience : extraction d'entités nommées avec GLiNER, un modèle
NER zero-shot (pas de prompt engineering, juste une liste de labels).

Sortie : JSON structuré { "entities": [ {text, label, start, end, score} ] }
"""

import json
from gliner import GLiNER

from config import CYBER_ENTITY_LABELS, GLINER_MODEL_NAME, GLINER_CONFIDENCE_THRESHOLD


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

    def extract(
        self, text: str, threshold: float = GLINER_CONFIDENCE_THRESHOLD
    ) -> dict:
        """Lance la prédiction NER et renvoie un dict prêt à sérialiser en JSON."""
        raw_entities = self.model.predict_entities(
            text, self.labels, threshold=threshold
        )

        entities = [
            {
                "text": e["text"],
                "label": e["label"],
                "start": e["start"],
                "end": e["end"],
                "score": round(float(e["score"]), 4),
            }
            for e in raw_entities
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
