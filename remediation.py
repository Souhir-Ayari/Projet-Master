"""
remediation.py
----------------
Step 7 du pipeline : boucle Propose -> Verify -> Revise, version MINIMALE
(Bloc 2 du plan) — transforme les cas récupérés par le retrieval (Step 6) en
un plan de remédiation pour une nouvelle attaque.

  Propose : UN appel LLM, prompt contraint aux cas récupérés. Chaque
            recommandation doit citer le ou les cas (C1, C2...) dont elle
            vient ; le modèle a le droit de ne rien recommander si aucun cas
            ne s'applique (honest null, même principe que Layer 2).
  Verify  : vérification de traçabilité SIMPLE et déterministe, en code, sans
            LLM — chaque recommandation doit (1) citer au moins un cas qui
            existe parmi les cas récupérés, (2) ce cas doit porter une
            mitigation, (3) le texte de la recommandation doit être ancré
            lexicalement dans la mitigation de ce cas. Un vérificateur LLM
            aurait les mêmes biais que le proposeur ; une règle en code est
            reproductible et citable dans le papier.
  Revise  : UNE seule itération (N=1), déclenchée seulement si Verify rejette
            au moins une recommandation. Le modèle reçoit les recommandations
            rejetées avec la raison du rejet et doit les corriger ou les
            retirer. Ce qui reste non traçable après la révision est ÉCARTÉ du
            plan final (et conservé à part dans le résultat, pour l'analyse).

Trois modes, qui sont les trois lignes de la Table IV (RQ3) :
  - "no_retrieval"   : single-shot, le modèle ne voit que l'attaque ;
  - "retrieval"      : Propose sur les cas récupérés, sans boucle ;
  - "retrieval_loop" : Propose + Verify + Revise (N=1).
Verify est calculé dans les TROIS modes, contre les MÊMES cas récupérés :
c'est ce qui rend le taux de traçabilité comparable d'une ligne à l'autre.
"""

import re

from config import MITIGATION_TYPES
from mistral_extractor import MistralExtractor, MistralGenerationError

MODES = ("no_retrieval", "retrieval", "retrieval_loop")

# Part minimale des mots porteurs de sens d'une recommandation qui doivent se
# retrouver dans la mitigation du cas cité. Mesuré sur le premier run réel :
# les recommandations fidèles recopient la mitigation (ancrage 1.0), alors
# qu'une révision a produit une défense HYBRIDE — la mitigation de C1 plus
# une défense inventée ("... using secure prompt templates with explicit
# separation") — ancrée à 0.5, que l'ancien seuil de 0.3 laissait passer.
# 0.6 exige qu'une majorité nette du contenu vienne du cas cité.
MIN_LEXICAL_SUPPORT = 0.6

# Deux recommandations dont les mots porteurs de sens se recouvrent à ce
# point (Jaccard) sont la même défense : la révision renvoie parfois une
# variante d'une recommandation déjà acceptée.
DUPLICATE_OVERLAP = 0.8

# Mots vides ignorés dans le calcul d'ancrage : sans ça, "the/of/to" et le
# vocabulaire commun du domaine ("model", "attack") suffiraient à faire
# passer n'importe quelle recommandation pour ancrée.
_STOP_WORDS = frozenset(
    "the of to and a an in on for by with that this is are can could be as at "
    "from or into it its their they which when where should must use using "
    "all any each such not only also more than other these those via "
    "attack attacks attacker model models llm llms system systems".split()
)

_CASE_ID_RE = re.compile(r"C(\d+)", re.IGNORECASE)


def content_words(text: str | None) -> set[str]:
    """Mots porteurs de sens d'un texte (minuscules, sans mots vides, > 2 lettres)."""
    if not text:
        return set()
    return {
        w
        for w in re.findall(r"[a-zA-Z][a-zA-Z\-']+", text.lower())
        if len(w) > 2 and w not in _STOP_WORDS
    }


def lexical_support(claim: str, evidence: str) -> float:
    """Part des mots porteurs de sens de `claim` présents dans `evidence`."""
    claim_words = content_words(claim)
    if not claim_words:
        return 0.0
    return len(claim_words & content_words(evidence)) / len(claim_words)


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
_TYPES_BLOCK = "\n".join(f"- {name} : {desc}" for name, desc in MITIGATION_TYPES.items())

_OUTPUT_FORMAT = """Réponds UNIQUEMENT avec un objet JSON, sans texte autour :
{{
  "recommendations": [
    {{
      "action": "<une mesure de défense concrète, 1 phrase, en anglais>",
      "mitigation_type": "<un des types ci-dessous, ou null>",
      "cited_cases": [{cited_example}]
    }}
  ]
}}

Types de mitigation autorisés :
{types}"""



def _output_format(cited_example: str) -> str:
    """
    Bloc de format JSON, avec ses accolades ré-échappées : il est inséré dans
    des prompts qui passent ensuite par .format(attack=..., cases=...).
    """
    block = _OUTPUT_FORMAT.format(cited_example=cited_example, types=_TYPES_BLOCK)
    return block.replace("{", "{{").replace("}", "}}")


PROMPT_PROPOSE_NO_RETRIEVAL = """Tu es un analyste en sécurité des systèmes d'IA.

Nouvelle attaque signalée :
"{attack}"

Propose au plus 3 mesures de défense concrètes contre cette attaque.
Si le texte ne décrit pas une attaque contre un système d'IA, renvoie une liste vide.

""" + _output_format(cited_example="")

PROMPT_PROPOSE_RETRIEVAL = """Tu es un analyste en sécurité des systèmes d'IA.

Nouvelle attaque signalée :
"{attack}"

Cas similaires extraits d'articles scientifiques (base de connaissance) :
{cases}

Propose au plus 3 mesures de défense contre la nouvelle attaque, en respectant
STRICTEMENT ces règles :
1. Chaque mesure doit reprendre une mitigation présente dans les cas ci-dessus.
   N'invente aucune défense qui n'y figure pas.
2. Chaque mesure cite dans "cited_cases" le ou les identifiants (C1, C2...) des
   cas dont elle provient. Un cas marqué "aucune mitigation" ne peut pas être cité.
3. Si aucun cas ne s'applique à la nouvelle attaque, renvoie une liste vide :
   une liste vide est une réponse correcte, une défense inventée ne l'est pas.

""" + _output_format(cited_example='"C1"')

PROMPT_REVISE = """Tu es un analyste en sécurité des systèmes d'IA.

Nouvelle attaque signalée :
"{attack}"

Cas similaires extraits d'articles scientifiques (base de connaissance) :
{cases}

Tu avais proposé des mesures de défense. Un vérificateur a REJETÉ les
suivantes, car elles ne sont pas traçables vers les cas ci-dessus :
{rejected}

Pour chaque mesure rejetée, soit tu la réécris pour qu'elle reprenne fidèlement
la mitigation d'un cas cité (avec son identifiant), soit tu la retires.
Ne renvoie QUE les mesures rejetées corrigées (pas celles déjà acceptées).
Si aucune ne peut être corrigée, renvoie une liste vide.

""" + _output_format(cited_example='"C1"')


def format_cases(cases: list[dict]) -> str:
    """Numérote les cas récupérés (C1, C2...) tels que le modèle les verra."""
    lines = []
    for i, case in enumerate(cases, 1):
        mitigation = case.get("mitigation_summary")
        mitigation_text = (
            f"[{case.get('mitigation_type') or 'type non validé'}] {mitigation}"
            if mitigation
            else "aucune mitigation"
        )
        lines.append(
            f"C{i} — catégorie {case.get('category') or 'non validée'} "
            f"(similarité {case.get('similarity_score', 0):.2f})\n"
            f"    attaque    : {case.get('attack_summary')}\n"
            f"    mitigation : {mitigation_text}"
        )
    return "\n".join(lines) if lines else "(aucun cas récupéré)"


# --------------------------------------------------------------------------- #
# Verify
# --------------------------------------------------------------------------- #
def _cited_indexes(cited_cases) -> list[int]:
    """["C1", "c2", 3] -> [0, 1, 2] (indices 0-based) ; ignore le reste."""
    if not isinstance(cited_cases, list):
        cited_cases = [cited_cases] if cited_cases else []
    indexes = []
    for ref in cited_cases:
        match = _CASE_ID_RE.search(str(ref)) if not isinstance(ref, int) else None
        number = ref if isinstance(ref, int) else (int(match.group(1)) if match else None)
        if number is not None and number - 1 not in indexes:
            indexes.append(number - 1)
    return indexes


def verify(recommendations: list[dict], cases: list[dict]) -> list[dict]:
    """
    Vérifie la traçabilité de chaque recommandation contre les cas récupérés.
    Renvoie une copie de chaque recommandation, annotée de :
      - "traceable" (bool), "reason" (pourquoi rejetée, None si acceptée),
      - "support" (meilleur ancrage lexical sur un cas cité valide),
      - "supported_by_any_case" : ancrage >= seuil sur N'IMPORTE QUEL cas, cité
        ou non. Permet de distinguer, en mode no_retrieval, une défense juste
        mais non citée (le modèle ne voyait pas les cas) d'une défense absente
        de la base.
    """
    verified = []
    for rec in recommendations:
        action = rec.get("action") or ""
        annotated = {**rec}

        best_any = max(
            (lexical_support(action, c.get("mitigation_summary") or "") for c in cases),
            default=0.0,
        )
        annotated["supported_by_any_case"] = best_any >= MIN_LEXICAL_SUPPORT

        indexes = _cited_indexes(rec.get("cited_cases"))
        valid = [i for i in indexes if 0 <= i < len(cases)]
        with_mitigation = [i for i in valid if cases[i].get("mitigation_summary")]
        support = max(
            (lexical_support(action, cases[i]["mitigation_summary"]) for i in with_mitigation),
            default=0.0,
        )
        annotated["support"] = round(support, 3)

        if not action.strip():
            reason = "recommandation vide"
        elif not indexes:
            reason = "aucun cas cité"
        elif not valid:
            reason = f"cas cité(s) inexistant(s) : {rec.get('cited_cases')}"
        elif not with_mitigation:
            reason = "le(s) cas cité(s) ne porte(nt) aucune mitigation"
        elif support < MIN_LEXICAL_SUPPORT:
            reason = (
                f"ancrage insuffisant dans la mitigation citée "
                f"({support:.2f} < {MIN_LEXICAL_SUPPORT})"
            )
        else:
            reason = None

        # Le type d'une recommandation traçable est celui de la mitigation
        # qu'elle reprend, déjà validé à Layer 2 : le modèle le réattribuait
        # sinon librement ("rendre public le fonctionnement interne" typé
        # detection_script). Le type proposé est conservé pour l'analyse.
        annotated["proposed_type"] = rec.get("mitigation_type")
        best_case = max(
            with_mitigation,
            key=lambda i: lexical_support(action, cases[i]["mitigation_summary"]),
            default=None,
        )
        if reason is None and best_case is not None:
            annotated["mitigation_type"] = cases[best_case].get("mitigation_type")
        elif rec.get("mitigation_type") not in MITIGATION_TYPES:
            annotated["mitigation_type"] = None  # même découplage que Layer 2

        annotated["traceable"] = reason is None
        annotated["reason"] = reason
        verified.append(annotated)
    return verified


def deduplicate(recommendations: list[dict]) -> tuple[list[dict], list[dict]]:
    """Garde la première occurrence de chaque défense ; renvoie (gardées, doublons)."""
    kept, duplicates = [], []
    for rec in recommendations:
        words = content_words(rec.get("action"))
        is_dup = any(
            words and (len(words & content_words(k.get("action"))) /
                       len(words | content_words(k.get("action")))) >= DUPLICATE_OVERLAP
            for k in kept
        )
        (duplicates if is_dup else kept).append(rec)
    return kept, duplicates


_FIELD_RE = {
    "action": re.compile(r'"action"\s*:\s*"((?:[^"\\]|\\.)*)"'),
    "mitigation_type": re.compile(r'"mitigation_type"\s*:\s*"?([a-z_]+)"?'),
    "cited_cases": re.compile(r'"cited_cases"\s*:\s*\[([^\]]*)\]'),
}


def salvage_recommendations(raw: str) -> list[dict]:
    """
    Repli quand la réponse n'est pas un JSON valide dans son ensemble :
    récupère les recommandations une par une, par champ. Constaté sur le
    premier run réel : une seule virgule manquante dans la 3e recommandation
    rendait tout le JSON invalide, et les deux premières — correctes — étaient
    perdues, ce qui comptait à tort comme une abstention.
    """
    recs = []
    for block in re.split(r'(?=\{\s*"action")', raw)[1:]:
        action = _FIELD_RE["action"].search(block)
        if not action:
            continue
        mtype = _FIELD_RE["mitigation_type"].search(block)
        cited = _FIELD_RE["cited_cases"].search(block)
        recs.append({
            "action": action.group(1),
            "mitigation_type": mtype.group(1) if mtype and mtype.group(1) != "null" else None,
            "cited_cases": [f"C{n}" for n in _CASE_ID_RE.findall(cited.group(1))] if cited else [],
        })
    return recs


def traceability_rate(verified: list[dict]) -> float | None:
    """Part de recommandations traçables ; None s'il n'y en a aucune (abstention)."""
    if not verified:
        return None
    return round(sum(r["traceable"] for r in verified) / len(verified), 3)


# --------------------------------------------------------------------------- #
# Propose / Revise
# --------------------------------------------------------------------------- #
class Remediator:
    def __init__(self, mistral: MistralExtractor = None):
        self.mistral = mistral or MistralExtractor()
        self.n_llm_calls = 0
        self.n_parse_errors = 0

    def _call(self, prompt: str) -> tuple[list[dict], str]:
        """
        Un appel LLM -> (recommandations parsées, réponse brute). Si le JSON
        est invalide, les recommandations sont récupérées une par une
        (salvage_recommendations) et l'incident est compté dans
        self.n_parse_errors : une réponse illisible ne doit jamais passer
        pour une abstention.
        """
        self.n_llm_calls += 1
        try:
            raw = self.mistral._generate(prompt)
        except MistralGenerationError as e:
            print(f"[⚠] Échec de génération : {e}")
            self.n_parse_errors += 1
            return [], f"<échec de génération : {e}>"
        parsed = self.mistral._parse_json_full(raw)
        if isinstance(parsed, dict) and "recommendations" in parsed:
            recs = parsed["recommendations"] or []
            return [r for r in recs if isinstance(r, dict)], raw
        self.n_parse_errors += 1
        salvaged = salvage_recommendations(raw)
        print(f"[⚠] JSON invalide : {len(salvaged)} recommandation(s) récupérée(s) une par une.")
        return salvaged, raw

    def propose(self, attack: str, cases: list[dict], use_retrieval: bool):
        if use_retrieval:
            prompt = PROMPT_PROPOSE_RETRIEVAL.format(attack=attack, cases=format_cases(cases))
        else:
            prompt = PROMPT_PROPOSE_NO_RETRIEVAL.format(attack=attack)
        return self._call(prompt)

    def revise(self, attack: str, cases: list[dict], rejected: list[dict]):
        rejected_block = "\n".join(
            f"- \"{r.get('action')}\" (cas cités : {r.get('cited_cases')}) "
            f"-> rejet : {r['reason']}"
            for r in rejected
        )
        prompt = PROMPT_REVISE.format(
            attack=attack, cases=format_cases(cases), rejected=rejected_block
        )
        return self._call(prompt)

    def run(
        self, attack: str, cases: list[dict], mode: str, min_similarity: float = 0.0
    ) -> dict:
        """
        Exécute un mode de la Table IV sur une attaque et ses cas récupérés.
        `cases` est toujours fourni (même en no_retrieval) : le modèle ne les
        voit pas dans ce mode, mais Verify s'en sert pour mesurer la
        traçabilité sur la même base que les deux autres modes.
        """
        if mode not in MODES:
            raise ValueError(f"Mode inconnu : {mode} (attendu : {MODES})")
        self.n_llm_calls = 0
        self.n_parse_errors = 0

        # Seuls les cas au-dessus du seuil de similarité (le même qui décide
        # tier2_would_trigger) sont assez proches pour fonder une défense.
        # Sans ce filtre, la requête hors domaine (tour Eiffel, 0.43)
        # recevait trois défenses "traçables" : fidèles à des cas... qui ne
        # parlent pas de la même chose. Verify compare les trois modes aux
        # MÊMES cas éligibles, pour que la traçabilité reste comparable.
        eligible = [c for c in cases if c.get("similarity_score", 0) >= min_similarity]
        result = {
            "mode": mode,
            "min_similarity": min_similarity,
            "n_eligible_cases": len(eligible),
            "abstained_no_case": False,
            "proposed": [],
            "raw_propose": None,
            "revised": None,
            "raw_revise": None,
            "revision_triggered": False,
        }

        if mode != "no_retrieval" and not eligible:
            # Abstention motivée, sans appel LLM : aucun cas assez proche,
            # donc aucune défense traçable possible.
            result["abstained_no_case"] = True
            proposed, raw_propose = [], None
        else:
            proposed, raw_propose = self.propose(
                attack, eligible, use_retrieval=mode != "no_retrieval"
            )
        cases = eligible
        verified = verify(proposed, cases)
        result["proposed"] = verified
        result["raw_propose"] = raw_propose

        # Rejets de la PREMIÈRE proposition, comptés dans les trois modes :
        # c'est ce que la boucle est censée faire baisser.
        result["n_rejected_initial"] = sum(not r["traceable"] for r in verified)

        final = verified
        result["dropped"] = []
        if mode == "retrieval_loop":
            rejected = [r for r in verified if not r["traceable"]]
            if rejected:
                result["revision_triggered"] = True
                revised, raw_revise = self.revise(attack, cases, rejected)
                revised_verified = verify(revised, cases)
                result["revised"] = revised_verified
                result["raw_revise"] = raw_revise
                accepted = [r for r in verified if r["traceable"]]
                final = accepted + revised_verified
            # N=1 : ce qui reste non traçable après l'unique révision est
            # écarté du plan final, mais conservé pour l'analyse.
            result["dropped"] = [r for r in final if not r["traceable"]]
            final = [r for r in final if r["traceable"]]

        final, duplicates = deduplicate(final)
        result["duplicates"] = duplicates
        result["final_plan"] = final
        result["n_recommendations"] = len(final)
        result["traceability_rate"] = traceability_rate(final)
        result["supported_rate"] = (
            round(sum(r["supported_by_any_case"] for r in final) / len(final), 3)
            if final
            else None
        )
        result["n_llm_calls"] = self.n_llm_calls
        result["n_parse_errors"] = self.n_parse_errors
        return result
