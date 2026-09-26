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
# retrouver dans la mitigation du cas cité. 0.3 tolère la reformulation
# (le modèle ne recopie pas mot pour mot) mais rejette une défense inventée,
# dont le vocabulaire ne recoupe pas celui du cas qu'elle prétend citer.
MIN_LEXICAL_SUPPORT = 0.3

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

        if rec.get("mitigation_type") not in MITIGATION_TYPES:
            annotated["mitigation_type"] = None  # même découplage que Layer 2

        annotated["traceable"] = reason is None
        annotated["reason"] = reason
        verified.append(annotated)
    return verified


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

    def _call(self, prompt: str) -> tuple[list[dict], str]:
        """Un appel LLM -> (recommandations parsées, réponse brute)."""
        self.n_llm_calls += 1
        try:
            raw = self.mistral._generate(prompt)
        except MistralGenerationError as e:
            print(f"[⚠] Échec de génération : {e}")
            return [], f"<échec de génération : {e}>"
        parsed = self.mistral._parse_json_full(raw)
        recs = parsed.get("recommendations", []) if isinstance(parsed, dict) else []
        return [r for r in recs if isinstance(r, dict)], raw

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

    def run(self, attack: str, cases: list[dict], mode: str) -> dict:
        """
        Exécute un mode de la Table IV sur une attaque et ses cas récupérés.
        `cases` est toujours fourni (même en no_retrieval) : le modèle ne les
        voit pas dans ce mode, mais Verify s'en sert pour mesurer la
        traçabilité sur la même base que les deux autres modes.
        """
        if mode not in MODES:
            raise ValueError(f"Mode inconnu : {mode} (attendu : {MODES})")
        self.n_llm_calls = 0

        proposed, raw_propose = self.propose(attack, cases, use_retrieval=mode != "no_retrieval")
        verified = verify(proposed, cases)
        result = {
            "mode": mode,
            "proposed": verified,
            "raw_propose": raw_propose,
            "revised": None,
            "raw_revise": None,
            "revision_triggered": False,
        }

        # Rejets de la PREMIÈRE proposition, comptés dans les trois modes :
        # c'est ce que la boucle est censée faire baisser.
        result["n_rejected_initial"] = sum(not r["traceable"] for r in verified)

        final = verified
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

        result["final_plan"] = final
        result["n_recommendations"] = len(final)
        result["traceability_rate"] = traceability_rate(final)
        result["supported_rate"] = (
            round(sum(r["supported_by_any_case"] for r in final) / len(final), 3)
            if final
            else None
        )
        result["n_llm_calls"] = self.n_llm_calls
        return result
