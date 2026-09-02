"""
methodology_extractor.py
--------------------------
Layer 2 : à partir d'un chunk de texte ET des entités que Layer 1 (GLiNER ou
Mistral, INCHANGÉ — voir config.py section 5) en a déjà extraites, résume
l'attaque et sa mitigation si le texte en décrit une concrète. Ne prend
jamais le texte brut seul : les entités déjà validées par Layer 1 servent
d'ancrage supplémentaire contre l'hallucination.

Steps 1-3 du plan méthodologie/mitigation :
  Step 1 : résumé attaque/mitigation ancré sur le texte + les entités Layer 1,
           avec sauvegarde JSONL immédiate (extract_from_chunks).
  Step 2 (validation, voir attack_taxonomy.py) : le "mitre_technique_id"
           proposé par le modèle est vérifié contre la short-list DU DOMAINE
           analysé (MITRE ATLAS pour "llm", MITRE ATT&CK pour
           "supply_chain") — jamais accepté tel quel, même principe que
           mistral_extractor._filter_valid_labels. Normalisé au préalable
           (_normalize_technique_id) : le modèle ajoute parfois le nom de la
           technique après l'ID ("AML.T0051.001: Indirect"), ce qui faisait
           échouer la validation d'un ID pourtant correct et effaçait
           silencieusement catégorie ET mitigation en aval.
  Step 3 : la mitigation est conservée dès que l'attaque est confirmée,
           QUE la catégorie soit validée ou non — un résumé de mitigation
           ancré sur le texte reste un signal réel même quand l'étape de
           catégorisation échoue à part (catégorie non validée -> null
           séparément, sans entraîner la mitigation avec elle). Les valeurs
           de remplissage ("non spécifié"...) sont rejetées via
           mistral_extractor.is_filler_text, réutilisée telle quelle.
           La mitigation est STRUCTURÉE : un couple (mitigation_type,
           mitigation_summary) plutôt qu'une phrase libre, le type étant
           validé contre config.MITIGATION_TYPES selon le même principe
           propose/valide que la catégorie MITRE.
"""

import json

import attack_taxonomy
from config import DEFAULT_DOMAIN, MITIGATION_TYPES, methodology_prompt
from jsonl_utils import append_jsonl
from mistral_extractor import MistralExtractor, MistralGenerationError, is_filler_text


def _normalize_technique_id(raw: str | None, domain: str = DEFAULT_DOMAIN) -> str | None:
    """
    Le modèle ajoute parfois le nom de la technique après l'ID
    ("AML.T0051.001: Indirect" au lieu de "AML.T0051.001"), ce qui fait
    échouer une comparaison stricte même quand l'ID lui-même est correct. On
    ne garde que le préfixe ID avant validation. Le format de l'ID dépend du
    référentiel du domaine (Txxxx vs AML.Txxxx), d'où la regex fournie par
    attack_taxonomy.id_prefix_pattern() plutôt qu'une constante locale.
    """
    if not raw:
        return None
    match = attack_taxonomy.id_prefix_pattern(domain).match(raw.strip().upper())
    return match.group(1) if match else None


def _normalize_mitigation_type(raw: str | None) -> str | None:
    """
    Le modèle renvoie parfois le type avec des espaces, une majuscule ou un
    tiret ("Filtering Rule", "filtering-rule") au lieu de la valeur exacte.
    On normalise avant de valider contre config.MITIGATION_TYPES ; tout ce
    qui ne tombe pas sur l'un des trois types autorisés devient None.
    """
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return candidate if candidate in MITIGATION_TYPES else None


class MethodologyExtractor:
    def __init__(
        self,
        mistral: MistralExtractor = None,
        techniques: dict = None,
        domain: str = DEFAULT_DOMAIN,
    ):
        """
        `mistral` : réutilise une instance existante (même backend déjà
        chargé) au lieu d'en recréer une — évite un second chargement de
        modèle si le backend est "transformers".
        `domain` : "llm" (MITRE ATLAS, défaut) ou "supply_chain" (MITRE
        ATT&CK). Détermine le référentiel, la short-list de techniques et le
        rôle annoncé au modèle dans le prompt.
        `techniques` : référentiel pré-chargé (voir
        attack_taxonomy.load_techniques()) ; chargé automatiquement sinon,
        ce qui peut déclencher un téléchargement au premier appel.
        """
        self.mistral = mistral or MistralExtractor()
        self.domain = domain
        self.techniques = (
            techniques
            if techniques is not None
            else attack_taxonomy.load_techniques(domain)
        )

    def extract(self, chunk_text: str, layer1_entities: list[dict]) -> dict:
        """
        Un seul appel au modèle produit attack_present, attack_summary,
        mitre_technique_id (candidat), mitigation_summary (candidat) et
        confidence (Step 1). Steps 2 et 3 sont appliqués APRÈS coup en code
        sur cette même réponse, plutôt que via des appels séparés — un
        aller-retour Ollama de plus par chunk coûterait cher sur CPU pour un
        gain marginal, et la validation post-hoc reste tout aussi stricte
        (le modèle ne peut jamais faire valider une catégorie inventée).
        """
        entities_block = self._format_entities(layer1_entities)
        mitre_labels = attack_taxonomy.shortlist_labels_block(
            self.domain, self.techniques
        )
        prompt = methodology_prompt(
            domain=self.domain,
            entities=entities_block,
            mitre_labels=mitre_labels,
            text=chunk_text,
        )

        try:
            raw_output = self.mistral._generate(prompt)
        except MistralGenerationError as e:
            print(
                f"[⚠] Chunk ignoré (méthodologie) après échec définitif de "
                f"génération : {e}"
            )
            raw_output = ""

        parsed = self.mistral._parse_json_full(raw_output)
        record = self._validate(parsed)
        record["raw_model_output"] = raw_output
        return record

    def _validate(self, parsed: dict) -> dict:
        attack_present = bool(parsed.get("attack_present", False))

        attack_summary = (
            self._clean_text_field(parsed.get("attack_summary"))
            if attack_present
            else None
        )

        # Step 2 : le modèle PROPOSE une technique, on VALIDE contre la
        # short-list du domaine (attack_taxonomy.LLM_THREAT_TECHNIQUE_IDS ou
        # SUPPLY_CHAIN_TECHNIQUE_IDS) — plus stricte qu'une simple
        # vérification d'existence dans le référentiel : un ID réel mais
        # hors-sujet pour ce domaine est rejeté ici aussi (voir le
        # commentaire au-dessus des short-lists). Normalisé d'abord
        # (_normalize_technique_id) : "AML.T0051.001: Indirect" doit valider
        # comme "AML.T0051.001".
        raw_technique_id = parsed.get("mitre_technique_id")
        normalized_technique_id = _normalize_technique_id(raw_technique_id, self.domain)
        technique_valid = attack_taxonomy.is_in_shortlist(
            normalized_technique_id, self.domain
        )
        if attack_present and raw_technique_id and not technique_valid:
            print(
                f"[⚠] mitre_technique_id proposé rejeté — hors de la "
                f"short-list {self.domain} autorisée : {raw_technique_id!r}"
                + (
                    f" (normalisé en {normalized_technique_id!r})"
                    if normalized_technique_id != raw_technique_id
                    else ""
                )
            )
        mitre_technique_id = (
            normalized_technique_id if attack_present and technique_valid else None
        )

        # Step 3 : la mitigation est conservée dès que l'attaque est
        # confirmée, indépendamment du succès de la catégorisation — un
        # résumé de mitigation ancré sur le texte est un signal réel même
        # quand l'étape de catégorisation échoue à part (ex: bug de parsing
        # d'ID, ou aucune technique de la short-list ne correspond). Coupler
        # les deux effaçait silencieusement une mitigation valide dès que la
        # catégorie ratait, pour une raison n'ayant souvent rien à voir avec
        # la qualité de la mitigation elle-même.
        mitigation_summary = None
        mitigation_type = None
        if attack_present:
            mitigation_summary = self._clean_text_field(
                parsed.get("mitigation_summary")
            )
            # Le type n'a de sens qu'accompagné d'un résumé : un type seul
            # ("filtering_rule" sans rien décrire) serait une catégorie vide.
            if mitigation_summary:
                raw_mitigation_type = parsed.get("mitigation_type")
                mitigation_type = _normalize_mitigation_type(raw_mitigation_type)
                if raw_mitigation_type and not mitigation_type:
                    # Résumé gardé quand même : même découplage que pour la
                    # catégorie MITRE ci-dessus — une défense réellement
                    # décrite dans le texte reste un signal exploitable même
                    # si elle n'entre dans aucun des trois types prévus (ex:
                    # une recommandation organisationnelle). Perdre le résumé
                    # parce que le type ne colle pas coûterait plus que de
                    # garder un type null.
                    print(
                        f"[⚠] mitigation_type proposé rejeté — hors des types "
                        f"autorisés {sorted(MITIGATION_TYPES)} : "
                        f"{raw_mitigation_type!r} (le résumé est conservé)"
                    )

        confidence = parsed.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = None

        return {
            "domain": self.domain,
            "attack_present": attack_present,
            "attack_summary": attack_summary,
            "mitre_technique_id": mitre_technique_id,
            "mitre_technique_name": attack_taxonomy.technique_name(
                mitre_technique_id, self.techniques, self.domain
            ),
            "mitigation_type": mitigation_type,
            "mitigation_summary": mitigation_summary,
            "confidence": confidence,
        }

    @staticmethod
    def _clean_text_field(value) -> str | None:
        """None si absent/vide/valeur de remplissage (honest null) plutôt qu'une chaîne creuse."""
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or is_filler_text(value):
            return None
        return value

    @staticmethod
    def _format_entities(entities: list[dict]) -> str:
        if not entities:
            return "(aucune entité extraite pour cet extrait)"
        return "\n".join(
            f'- "{e.get("text", "")}" ({e.get("label", "")})' for e in entities
        )

    def extract_from_chunks(
        self,
        chunks: list[str],
        layer1_entities_per_chunk: list[list[dict]],
        source_paper: str = None,
        jsonl_path: str = None,
    ) -> list[dict]:
        """
        Applique extract() chunk par chunk. Si jsonl_path est fourni, chaque
        enregistrement est sauvegardé IMMÉDIATEMENT après génération : un run
        interrompu en cours de route laisse quand même tout ce qui a déjà été
        produit inspectable à la main, plutôt que perdu dans une structure en
        mémoire jamais écrite sur disque.
        """
        if len(chunks) != len(layer1_entities_per_chunk):
            raise ValueError(
                f"chunks ({len(chunks)}) et layer1_entities_per_chunk "
                f"({len(layer1_entities_per_chunk)}) doivent avoir la même longueur"
            )
        records = []
        n = len(chunks)
        for i, (chunk, entities) in enumerate(
            zip(chunks, layer1_entities_per_chunk), start=1
        ):
            print(f"    [méthodologie] chunk {i}/{n} ...", end=" ", flush=True)
            record = self.extract(chunk, entities)
            record["chunk_index"] = i - 1
            record["source_paper"] = source_paper
            print("attaque détectée" if record["attack_present"] else "pas d'attaque")
            if jsonl_path:
                append_jsonl(jsonl_path, record)
            records.append(record)
        return records


if __name__ == "__main__":
    sample_text = (
        "The attacker plants instructions inside a web page that the assistant "
        "later retrieves, causing it to exfiltrate the contents of the user's "
        "session. The authors mitigate this by wrapping retrieved content in "
        "explicit delimiters and restating the system instructions after it."
    )
    sample_entities = [
        {"text": "web page", "label": "vecteur d'entrée"},
        {"text": "exfiltrate the contents", "label": "impact sur le modèle"},
        {"text": "explicit delimiters", "label": "défense ou garde-fou cité"},
    ]
    extractor = MethodologyExtractor()  # domaine "llm" par défaut
    result = extractor.extract(sample_text, sample_entities)
    print(json.dumps(result, indent=2, ensure_ascii=False))
