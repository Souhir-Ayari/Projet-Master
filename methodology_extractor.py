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
           proposé par le modèle est vérifié contre la short-list
           supply-chain — jamais accepté tel quel, même principe que
           mistral_extractor._filter_valid_labels. Normalisé au préalable
           (_normalize_technique_id) : le modèle ajoute parfois le nom de la
           technique après l'ID ("T1190: Exploit Public-Facing Application"),
           ce qui faisait échouer la validation d'un ID pourtant correct et
           effaçait silencieusement catégorie ET mitigation en aval.
  Step 3 : la mitigation est conservée dès que l'attaque est confirmée,
           QUE la catégorie soit validée ou non — un résumé de mitigation
           ancré sur le texte reste un signal réel même quand l'étape de
           catégorisation échoue à part (catégorie non validée -> null
           séparément, sans entraîner la mitigation avec elle). Les valeurs
           de remplissage ("non spécifié"...) sont rejetées via
           mistral_extractor.is_filler_text, réutilisée telle quelle.
"""

import json
import re

import attack_taxonomy
from config import PROMPT_METHODOLOGY
from jsonl_utils import append_jsonl
from mistral_extractor import MistralExtractor, MistralGenerationError, is_filler_text

_ID_PREFIX_RE = re.compile(r"^(T\d{4}(?:\.\d{3})?)")


def _normalize_technique_id(raw: str | None) -> str | None:
    """
    Le modèle ajoute parfois le nom de la technique après l'ID
    ("T1190: Exploit Public-Facing Application" au lieu de "T1190"), ce qui
    fait échouer une comparaison stricte même quand l'ID lui-même est
    correct. On ne garde que le préfixe ID avant validation.
    """
    if not raw:
        return None
    match = _ID_PREFIX_RE.match(raw.strip().upper())
    return match.group(1) if match else None


class MethodologyExtractor:
    def __init__(self, mistral: MistralExtractor = None, techniques: dict = None):
        """
        `mistral` : réutilise une instance existante (même backend déjà
        chargé) au lieu d'en recréer une — évite un second chargement de
        modèle si le backend est "transformers".
        `techniques` : référentiel MITRE ATT&CK pré-chargé (voir
        attack_taxonomy.load_techniques()) ; chargé automatiquement sinon,
        ce qui peut déclencher un téléchargement au premier appel.
        """
        self.mistral = mistral or MistralExtractor()
        self.techniques = (
            techniques if techniques is not None else attack_taxonomy.load_techniques()
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
        mitre_labels = attack_taxonomy.supply_chain_labels_block(self.techniques)
        prompt = PROMPT_METHODOLOGY.format(
            text=chunk_text, entities=entities_block, mitre_labels=mitre_labels
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
        # short-list supply-chain (attack_taxonomy.SUPPLY_CHAIN_TECHNIQUE_IDS)
        # — plus stricte qu'une simple vérification d'existence dans MITRE
        # ATT&CK : un ID réel mais hors-sujet pour ce domaine est rejeté ici
        # aussi (voir le commentaire au-dessus de SUPPLY_CHAIN_TECHNIQUE_IDS).
        # Normalisé d'abord (_normalize_technique_id) : "T1190: Exploit
        # Public-Facing Application" doit valider comme "T1190".
        raw_technique_id = parsed.get("mitre_technique_id")
        normalized_technique_id = _normalize_technique_id(raw_technique_id)
        technique_valid = attack_taxonomy.is_valid_supply_chain_technique_id(
            normalized_technique_id
        )
        if attack_present and raw_technique_id and not technique_valid:
            print(
                f"[⚠] mitre_technique_id proposé rejeté — hors de la "
                f"short-list supply-chain autorisée : {raw_technique_id!r}"
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
        if attack_present:
            mitigation_summary = self._clean_text_field(
                parsed.get("mitigation_summary")
            )

        confidence = parsed.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = None

        return {
            "attack_present": attack_present,
            "attack_summary": attack_summary,
            "mitre_technique_id": mitre_technique_id,
            "mitre_technique_name": attack_taxonomy.technique_name(
                mitre_technique_id, self.techniques
            ),
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
        "In 2024, investigators uncovered a multi-stage backdoor in the XZ "
        "Utils compression library (CVE-2024-3094), introduced through social "
        "engineering of a maintainer. HCMRs require SLSA-level provenance to "
        "prevent similar opaque build manipulation."
    )
    sample_entities = [
        {"text": "CVE-2024-3094", "label": "identifiant CVE"},
        {"text": "XZ Utils", "label": "paquet ou bibliothèque logicielle concerné"},
        {"text": "SLSA", "label": "framework ou mécanisme de mitigation"},
    ]
    extractor = MethodologyExtractor()
    result = extractor.extract(sample_text, sample_entities)
    print(json.dumps(result, indent=2, ensure_ascii=False))
