"""
hybrid_extractor.py
--------------------
CAS BONUS : le "combo idéal" évoqué dans votre protocole.

Idée : GLiNER est rapide et factuel (il ne peut extraire que du texte présent
dans le document, donc hallucination ~0 par construction) mais moins flexible
sémantiquement. Mistral 7B avec prompt engineering est plus intelligent
(comprend le contexte, les synonymes, la relation entre entités) mais peut
halluciner.

Pipeline hybride :
  1. GLiNER extrait un premier jeu d'entités "sûres" (candidats).
  2. Mistral reçoit le texte + les candidats GLiNER, et a pour instruction de
     (a) valider/rejeter chaque candidat, (b) compléter avec des entités
     manquantes, en restant strictement ancré au texte.
Cela combine le rappel du LLM et la précision du NER pur.
"""

import json
import re

from gliner_extractor import GLiNERExtractor
from mistral_extractor import MistralExtractor
from config import CYBER_ENTITY_LABELS

HYBRID_PROMPT = """Tu es un analyste SOC. Voici un texte et une liste d'entités candidates
déjà détectées par un modèle NER. Ta tâche :
1. Valide chaque candidat s'il est correct et pertinent en cybersécurité.
2. Rejette les candidats incorrects ou hors contexte.
3. Ajoute des entités manquantes UNIQUEMENT si elles apparaissent explicitement
   dans le texte (aucune invention).

Catégories valides : {labels}

Texte :
\"\"\"
{text}
\"\"\"

Candidats détectés par le NER :
{candidates}

Réponds uniquement avec un JSON au format :
{{
  "entities": [
    {{"text": "...", "label": "...", "source": "validated|added"}}
  ]
}}

JSON :"""


class HybridExtractor:
    def __init__(self, gliner: GLiNERExtractor = None, mistral: MistralExtractor = None):
        self.gliner = gliner or GLiNERExtractor()
        self.mistral = mistral or MistralExtractor()

    def extract(self, text: str) -> dict:
        gliner_result = self.gliner.extract(text)
        candidates_str = "\n".join(
            f"- \"{e['text']}\" ({e['label']})" for e in gliner_result["entities"]
        ) or "(aucun candidat détecté)"

        prompt = HYBRID_PROMPT.format(
            labels="\n".join(f"- {l}" for l in CYBER_ENTITY_LABELS),
            text=text,
            candidates=candidates_str,
        )

        raw_output = self.mistral._generate(prompt)
        entities = self.mistral._parse_json_output(raw_output)

        return {
            "method": "hybrid_gliner_then_mistral",
            "gliner_candidates": gliner_result["entities"],
            "entities": entities,
            "raw_model_output": raw_output,
        }


if __name__ == "__main__":
    sample_text = (
        "The APT group Lazarus exploited CVE-2023-23397 to compromise servers "
        "at 185.220.101.5 and deploy the malware Emotet."
    )
    hybrid = HybridExtractor()
    output = hybrid.extract(sample_text)
    print(json.dumps(output, indent=2, ensure_ascii=False))
