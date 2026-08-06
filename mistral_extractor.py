"""
mistral_extractor.py
---------------------
CAS 2 de l'expérience : extraction d'entités via Mistral 7B guidé par prompt
(prompt-based extraction). Deux variantes de prompt sont disponibles
("naive" et "engineered") pour mesurer l'impact du prompt engineering,
comme demandé dans le protocole expérimental.

Deux backends supportés :
  - Ollama (recommandé, simple : `ollama pull mistral` puis `ollama serve`)
  - HuggingFace transformers (nécessite un GPU avec assez de VRAM)
"""

import json
import re
import time
import requests
from typing import ClassVar


from config import (
    PROMPTS,
    CYBER_ENTITY_LABELS,
    SUPPLY_CHAIN_ENTITY_LABELS,
    SUPPLY_CHAIN_ENTITY_DESCRIPTIONS,
    TEMPLATE_LEAK_VALUES,
    MISTRAL_BACKEND,
    OLLAMA_MODEL_NAME,
    OLLAMA_URL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_MAX_RETRIES,
    HF_MODEL_NAME,
    build_labels_block,
    is_format_valid,
)


class MistralGenerationError(Exception):
    """Levée quand Ollama échoue définitivement sur un chunk (timeout/erreur
    réseau), après épuisement des tentatives. Interceptée dans extract() pour
    que l'échec d'UN chunk n'arrête pas tout le run — voir extract()."""


class MistralExtractor:
    def __init__(self, backend: str = MISTRAL_BACKEND):
        self.backend = backend
        self._hf_pipeline = None

        if backend == "transformers":
            self._load_transformers_model()

    # ------------------------------------------------------------------ #
    # Backend HuggingFace transformers (optionnel, nécessite un GPU)
    # ------------------------------------------------------------------ #
    def _load_transformers_model(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer 
        import torch

        print(f"[Mistral] Chargement de {HF_MODEL_NAME} via transformers ...")
        self.tokenizer = AutoTokenizer.from_pretrained(HF_MODEL_NAME)
        self.model = AutoModelForCausalLM.from_pretrained(
            HF_MODEL_NAME,
            torch_dtype=torch.float16,
            device_map="auto",
        )

    def _generate_transformers(self, prompt: str, max_new_tokens: int = 700) -> str:
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.1,  # basse température : on veut de la précision, pas de créativité
            do_sample=False,
        )
        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return text[len(prompt) :]  # ne garder que la complétion

    # ------------------------------------------------------------------ #
    # Backend Ollama (recommandé)
    # ------------------------------------------------------------------ #
    def _generate_ollama(self, prompt: str) -> str:
        """
        Appelle Ollama. En cas de timeout ou d'erreur réseau (fréquent sur CPU
        avec des chunks longs), retente OLLAMA_MAX_RETRIES fois avant
        d'abandonner ce chunk précis via MistralGenerationError — plutôt que de
        laisser l'exception remonter et planter tout le script en cours de run
        (ce qui faisait perdre toute la progression déjà faite sur les chunks
        précédents).
        """
        last_error = None
        for attempt in range(OLLAMA_MAX_RETRIES + 1):
            try:
                response = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL_NAME,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1},
                    },
                    timeout=OLLAMA_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return response.json()["response"]
            except (requests.exceptions.RequestException, TimeoutError, OSError) as e:
                last_error = e
                if attempt < OLLAMA_MAX_RETRIES:
                    print(
                        f"[⚠] Timeout/erreur Ollama (tentative {attempt + 1}/{OLLAMA_MAX_RETRIES + 1}) : {e}. Nouvelle tentative dans 5s..."
                    )
                    time.sleep(5)
        raise MistralGenerationError(
            f"Échec après {OLLAMA_MAX_RETRIES + 1} tentative(s) : {last_error}"
        )

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str) -> str:
        if self.backend == "ollama":
            return self._generate_ollama(prompt)
        elif self.backend == "transformers":
            return self._generate_transformers(prompt)
        else:
            raise ValueError(f"Backend inconnu : {self.backend}")

    def extract(
        self, text: str, prompt_variant: str = "engineered", user_need: str = None
    ) -> dict:
        """
        Extrait les entités via prompt.
        prompt_variant = "naive" | "engineered" | "custom" | "topic".

        - "naive"/"engineered" : taxonomie générique CYBER_ENTITY_LABELS.
        - "custom"  : besoin de l'utilisateur (voir user_need), taxonomie
          générique en référence secondaire.
        - "topic"   : taxonomie SUPPLY_CHAIN_ENTITY_LABELS, spécifique aux
          attaques de chaîne d'approvisionnement logicielle / backdoors
          (ex: XZ Utils, SolarWinds, Log4Shell) — à utiliser quand le
          document analysé porte précisément sur ce sujet, pour comparer
          la précision d'un prompt généraliste vs un prompt spécialisé.

        user_need : description en langage naturel de ce que l'utilisateur veut
        extraire (ex: "extrais uniquement les CVE et les adresses IP mentionnées",
        ou "liste les logiciels/versions vulnérables cités"). Utilisé
        uniquement si prompt_variant == "custom" ; ignoré sinon.
        """
        template = PROMPTS[prompt_variant]
        if prompt_variant == "topic":
            labels_for_prompt = SUPPLY_CHAIN_ENTITY_LABELS
            descriptions_for_prompt = SUPPLY_CHAIN_ENTITY_DESCRIPTIONS
        elif prompt_variant == "custom" and user_need:
            # Restreint la liste de labels AVANT même que le modèle ne la voie :
            # sans ça, le modèle a tendance à vouloir "remplir" chacune des 23
            # catégories génériques avec une entité inventée, même quand le
            # besoin ne porte que sur 2-3 d'entre elles (ex: CVE + logiciels).
            # Complète le fix #6 (auto-identification + post-filtre a posteriori)
            # en réduisant le problème à la source.
            labels_for_prompt = self._select_relevant_labels(
                user_need, CYBER_ENTITY_LABELS
            )
            descriptions_for_prompt = None
        else:
            labels_for_prompt = CYBER_ENTITY_LABELS
            descriptions_for_prompt = (
                None  # -> ENTITY_DESCRIPTIONS par défaut dans build_labels_block
            )
        format_kwargs = {
            "text": text,
            "labels": build_labels_block(labels_for_prompt, descriptions_for_prompt),
            "user_need": user_need or "(aucun besoin spécifique fourni)",
        }
        prompt = template.format(**format_kwargs)

        try:
            raw_output = self._generate(prompt)
        except MistralGenerationError as e:
            print(f"[⚠] Chunk ignoré après échec définitif de génération : {e}")
            raw_output = ""  # -> parsed restera {} pour ce chunk, le run continue

        parsed = self._parse_json_full(raw_output)
        if parsed and not isinstance(parsed.get("entities"), list):
            preview = raw_output.strip().replace("\n", " ")[:200]
            print(
                f"[⚠] JSON parsé mais sans clé \"entities\" exploitable "
                f"(clés trouvées : {list(parsed.keys())}). Le modèle a "
                f"peut-être utilisé un autre nom de champ. "
                f"Extrait de la réponse brute : {preview!r}"
            )
        entities = parsed.get("entities", [])

        # Filtre 1 : rejette les labels hors taxonomie (fix #2)
        entities = self._filter_valid_labels(entities, labels_for_prompt)

        # Filtre 2 : pour "custom", restreint aux catégories que le modèle a
        # lui-même identifiées comme pertinentes pour user_need (fix #6) —
        # rend vérifiable côté code la consigne "n'utilise QUE ces catégories"
        if prompt_variant == "custom":
            entities = self._filter_by_relevant_categories(
                entities, parsed.get("relevant_categories")
            )

        # Filtre 3 : rejette les entités dont le format ne respecte pas le
        # pattern attendu pour leur label (ex: "CVE-not found" ou
        # "CVE-[0-9]{4}" pour un label "identifiant CVE") — applique
        # is_format_valid, jusqu'ici défini dans config.py mais jamais branché.
        entities = self._filter_by_format(entities)

        # Filtre 4 : rejette les valeurs d'exemple FICTIVES recopiées depuis
        # le prompt (ex: "CVE-0000-00000", "0.0.0.0") — remplacer les
        # exemples réalistes par des valeurs fictives dans le prompt ne
        # suffit pas, le modèle les recopie parfois quand même malgré la
        # consigne. Ce filtre attrape la fuite après coup, quelle que soit
        # la valeur d'exemple choisie (voir config.TEMPLATE_LEAK_VALUES).
        entities = self._drop_template_leaks(entities)

        method_name = f"mistral_prompt_{prompt_variant}"

        return {
            "method": method_name,
            "user_need": user_need if prompt_variant == "custom" else None,
            "entities": entities,
            "raw_model_output": raw_output,  # utile pour debug / audit d'hallucination
        }

    def extract_from_chunks(
        self,
        chunks: list[str],
        prompt_variant: str = "engineered",
        user_need: str = None,
    ) -> dict:
        all_entities = []
        seen = set()
        raw_outputs = []
        n = len(chunks)
        for i, chunk in enumerate(chunks, start=1):
            print(f"    chunk {i}/{n} ...", end=" ", flush=True)
            result = self.extract(chunk, prompt_variant, user_need=user_need)
            print(f"{len(result['entities'])} entité(s)")
            raw_outputs.append(result["raw_model_output"])
            for e in result["entities"]:
                key = (e.get("text", "").lower(), e.get("label", ""))
                if key not in seen:
                    seen.add(key)
                    all_entities.append(e)
        return {
            "method": f"mistral_prompt_{prompt_variant}",
            "user_need": user_need if prompt_variant == "custom" else None,
            "entities": all_entities,
            "raw_model_output": raw_outputs,
        }

    @staticmethod
    def _parse_json_full(raw_output: str) -> dict:
        """
        Les LLM ajoutent parfois du texte avant/après le JSON malgré la consigne.
        On extrait le premier objet JSON valide trouvé dans la réponse, et on
        renvoie l'objet COMPLET (pas seulement "entities") pour pouvoir aussi
        lire le champ "relevant_categories" (variant custom, fix #6).

        Avant ce fix, un échec de parsing (aucun JSON trouvé, ou JSON malformé)
        renvoyait silencieusement {} : impossible de distinguer "le modèle n'a
        rien trouvé" de "le modèle a répondu mais le parsing a échoué" en
        regardant seulement le nombre d'entités (0 dans les deux cas). C'est
        le cas typique du prompt "naive", qui ne force aucun format JSON —
        on log donc désormais un avertissement avec un extrait de la réponse
        brute pour pouvoir diagnostiquer sans devoir aller lire
        raw_model_output dans le JSON de sortie à chaque fois.
        """
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if not match:
            preview = raw_output.strip().replace("\n", " ")[:200]
            print(
                f"[⚠] Aucun JSON trouvé dans la réponse du modèle. "
                f"Extrait de la réponse brute : {preview!r}"
            )
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            preview = match.group(0).strip().replace("\n", " ")[:200]
            print(
                f"[⚠] JSON trouvé mais invalide ({e}). "
                f"Extrait : {preview!r}"
            )
            return {}

    @staticmethod
    def _parse_json_output(raw_output: str) -> list[dict]:
        """Compatibilité : ne renvoie que la liste d'entités."""
        return MistralExtractor._parse_json_full(raw_output).get("entities", [])

    # Mots vides à ignorer lors du découpage des noms de labels : sans ce filtre,
    # "de"/"ou"/"la" matcheraient quasiment n'importe quel besoin utilisateur en
    # français, ce qui viderait le filtrage de tout son sens (il sélectionnerait
    # presque toujours la totalité des 23 labels).
    


    _STOPWORDS_LABELS: ClassVar[frozenset[str]] = frozenset(
        {
            "de",
            "du",
            "des",
            "la",
            "le",
            "les",
            "l'",
            "d'",   
            "un",
            "une",
            "ou",
            "et",
            "à",
            "au",
            "aux",
            "en",
            "par",
            "pour",
            "sur",
            "avec",
        }
    )
    @staticmethod
    def _select_relevant_labels(user_need: str, all_labels: list[str]) -> list[str]:
        """
        Restreint la liste de labels AVANT de construire le prompt "custom", en
        ne gardant que les catégories dont un mot significatif du nom apparaît
        dans le besoin utilisateur. Complète le fix #6 (auto-identification +
        post-filtre a posteriori) en réduisant le problème à la source : si le
        modèle ne VOIT même pas les 23 catégories génériques, il ne peut plus
        essayer de "remplir" chacune d'elles avec une entité inventée.

        Filtrage par mot-clé simple (fallback rapide, pas la solution
        définitive) — les mots vides (de/ou/la/...) sont ignorés pour éviter
        un faux-positif quasi systématique en français. Une version plus
        fiable utiliserait un petit appel LLM dédié à la sélection des 2-3
        labels pertinents avant de construire le prompt final.
        """
        need_lower = user_need.lower()
        selected = []
        for label in all_labels:
            words = [
                w
                for w in label.lower().split()
                if w not in MistralExtractor._STOPWORDS_LABELS and len(w) > 1
            ]
            if any(word in need_lower for word in words):
                selected.append(label)
        return (
            selected or all_labels
        )  # fallback : aucun match -> on garde tout plutôt que rien

    @staticmethod
    def _filter_valid_labels(
        entities: list[dict], allowed_labels: list[str]
    ) -> list[dict]:
        """
        Rejette toute entité dont le label n'est PAS dans la taxonomie autorisée
        pour ce variant de prompt (labels_for_prompt). Sans ce filtre, un modèle
        qui invente des labels hors taxonomie (ex: "incident", "référence à une
        source") produit des faux positifs automatiques qui font chuter la
        précision, même quand le texte extrait lui-même est correct.
        """
        allowed = set(allowed_labels)
        valid, rejected = [], []
        for e in entities:
            (valid if e.get("label") in allowed else rejected).append(e)
        if rejected:
            print(
                f"[⚠] {len(rejected)} entité(s) rejetée(s) — label hors taxonomie : "
                f"{[e.get('label') for e in rejected]}"
            )
        return valid

    @staticmethod
    def _filter_by_relevant_categories(
        entities: list[dict], relevant_categories
    ) -> list[dict]:
        """
        Pour le variant "custom" (fix #6) : restreint les entités aux catégories
        que le modèle a lui-même explicitement identifiées comme pertinentes
        pour le besoin utilisateur (champ "relevant_categories" du JSON, voir
        règle 7 de PROMPT_CUSTOM). Rend vérifiable côté code la consigne
        "n'utilise QUE ces catégories" plutôt que de compter uniquement sur le
        modèle pour la respecter spontanément.
        """
        if not relevant_categories or not isinstance(relevant_categories, list):
            # Le modèle n'a pas renvoyé ce champ (ou mal formé) -> on ne filtre
            # pas davantage ici ; _filter_valid_labels a déjà fait un premier tri.
            return entities
        allowed = set(relevant_categories)
        valid, rejected = [], []
        for e in entities:
            (valid if e.get("label") in allowed else rejected).append(e)
        if rejected:
            print(
                f"[⚠] {len(rejected)} entité(s) rejetée(s) — hors des catégories "
                f"jugées pertinentes par le modèle lui-même pour ce besoin "
                f"({sorted(allowed)}) : {[e.get('label') for e in rejected]}"
            )
        return valid

    @staticmethod
    def _filter_by_format(entities: list[dict]) -> list[dict]:
        """
        Rejette les entités dont le format ne correspond pas au pattern attendu
        pour leur label (ex: un label "identifiant CVE" dont le texte est
        "CVE-not found" ou "CVE-[0-9]{4}" au lieu d'un vrai CVE-AAAA-NNNNN).
        Utilise is_format_valid (config.py) : renvoie None (pas de pattern
        défini pour ce label, ex: "organisation victime") -> on garde l'entité
        faute de pouvoir vérifier ; renvoie False -> on rejette.
        """
        valid, rejected = [], []
        for e in entities:
            result = is_format_valid(e.get("label", ""), e.get("text", ""))
            (rejected if result is False else valid).append(e)
        if rejected:
            print(
                f"[⚠] {len(rejected)} entité(s) rejetée(s) — format invalide pour leur label : "
                f"{[(e.get('text'), e.get('label')) for e in rejected]}"
            )
        return valid

    @staticmethod
    def _drop_template_leaks(entities: list[dict]) -> list[dict]:
        """
        Rejette les entités dont le texte est une valeur d'exemple FICTIVE
        recopiée depuis le prompt (voir config.TEMPLATE_LEAK_VALUES, ex:
        "CVE-0000-00000", "0.0.0.0"). Complète les règles anti-hallucination
        écrites dans le prompt lui-même : un modèle recopie parfois
        l'exemple tel quel malgré la consigne "ne jamais les recopier",
        même quand ce n'est plus une valeur réaliste. Ce filtre attrape
        la fuite déterministe après coup, indépendamment de la valeur
        d'exemple choisie dans le prompt.
        """
        valid, rejected = [], []
        for e in entities:
            text = e.get("text", "").strip().lower()
            (rejected if text in TEMPLATE_LEAK_VALUES else valid).append(e)
        if rejected:
            print(
                f"[⚠] {len(rejected)} entité(s) rejetée(s) — valeur d'exemple fictive "
                f"recopiée depuis le prompt : {[e.get('text') for e in rejected]}"
            )
        return valid


if __name__ == "__main__":
    sample_text = (
        "The APT group Lazarus exploited CVE-2023-23397 to compromise servers "
        "at 185.220.101.5 and deploy the malware Emotet. The email admin@corp.fr "
        "was used for phishing."
    )
    extractor = MistralExtractor(backend="ollama")
    output = extractor.extract(sample_text, prompt_variant="engineered")
    print(json.dumps(output, indent=2, ensure_ascii=False))
