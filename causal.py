"""
causal.py
-----------
Adaptation CAUSALE des cas récupérés et vérificateur associé (Step 7, demande
de l'encadrante du 29/09).

Problème de la version précédente : Propose recopiait la mitigation du cas
cité, et le vérificateur lexical (60 % des mots de la recommandation présents
dans la mitigation) récompensait justement la copie. Une recommandation
ADAPTÉE à la nouvelle attaque — qui nomme ce qu'elle vise dans CETTE attaque —
était rejetée parce qu'elle n'était plus une copie.

Principe :
  1. La nouvelle attaque est décrite comme une chaîne causale à trois
     maillons : vecteur d'entrée -> mécanisme de contournement -> impact.
  2. Propose (adaptation) : pour chaque mitigation reprise d'un cas, le modèle
     indique quel maillon de la NOUVELLE chaîne elle casse ("broken_link") et
     la reformule pour cette attaque. Une mitigation qui ne casse aucun
     maillon ("none") est rejetée : elle ne s'applique pas.
  3. Verify, trois variantes (ablation demandée) :
       rule    la règle seule : sémantique (la recommandation reste impliquée
               par la mitigation citée) + maillon déduit par similarité ;
       labels  le modèle étiquette le maillon, la règle décide (configuration
               principale) : étiquette valide, maillon présent dans la chaîne,
               recommandation proche de ce maillon, et support sémantique ;
       llm     le modèle juge tout (même modèle que Propose : c'est aussi la
               référence "auto-critique" dont la littérature montre le biais).
     L'ancrage n'est plus lexical mais SÉMANTIQUE : similarité cosinus entre
     les embeddings (nomic-embed-text, déjà utilisé par le retrieval) de la
     recommandation et de la mitigation citée. Une reformulation adaptée garde
     un sens proche sans recopier les mots.
  4. Branche non ancrée : quand aucun cas ne passe le seuil θ, le système
     propose quand même des mesures, explicitement marquées NON ANCRÉES et
     jamais comptées comme traçables (au lieu d'une abstention muette).

Métriques :
  taux d'adaptation   part des recommandations finales qui mentionnent un
                      élément de la nouvelle attaque absent de la mitigation
                      citée (adaptée, et non recopiée) ;
  adéquation causale  part des recommandations finales dont le maillon cassé
                      existe dans la chaîne de la requête et dont le texte est
                      proche de ce maillon.

Les seuils ci-dessous sont fixés A PRIORI, avant tout run sur les requêtes
d'évaluation ; leur sensibilité est à rapporter, pas à ajuster sur le test.
"""

import re

LINKS = ("input_vector", "bypass_mechanism", "impact")
VERIFIERS = ("rule", "labels", "llm")

# Cosinus minimal recommandation / mitigation citée pour que la mitigation
# "implique" encore la recommandation. Avec nomic-embed-text, une
# reformulation fidèle dépasse nettement 0.7 ; deux défenses différentes du
# même domaine restent autour de 0.5-0.6.
SEMANTIC_MIN = 0.70
# Cosinus minimal recommandation / maillon cassé : la recommandation doit
# parler de ce maillon de la nouvelle attaque.
LINK_MIN = 0.50

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']+")
_STOP = frozenset(
    "the of to and a an in on for by with that this is are can could be as at from or into it its "
    "their they which when where should must use using all any each such not only also more than "
    "other these those via new attack attacks attacker model models llm llms system systems "
    "application applications user users data input inputs".split()
)


def _words(text: str | None) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2 and w not in _STOP}


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(float(x) * float(y) for x, y in zip(a, b))
    da = sum(float(x) ** 2 for x in a) ** 0.5
    db = sum(float(y) ** 2 for y in b) ** 0.5
    return float(num / (da * db)) if da and db else 0.0


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
PROMPT_CHAIN = """Tu es un analyste en sécurité des systèmes d'IA.

Décris l'attaque ci-dessous comme une chaîne causale à trois maillons, avec des
expressions courtes reprises du texte :
- input_vector : par où l'entrée malveillante arrive (ex. page web lue par l'assistant) ;
- bypass_mechanism : comment elle contourne les protections ou détourne le modèle ;
- impact : ce que l'attaquant obtient.
Mets null pour un maillon que le texte ne permet pas d'identifier.

Attaque : "{attack}"

Réponds UNIQUEMENT avec un JSON : {{"input_vector": ..., "bypass_mechanism": ..., "impact": ...}}
JSON :"""

PROMPT_ADAPT = """Tu es un analyste en sécurité des systèmes d'IA.

Nouvelle attaque signalée :
"{attack}"

Sa chaîne causale :
- input_vector : {input_vector}
- bypass_mechanism : {bypass_mechanism}
- impact : {impact}

Cas similaires extraits d'articles scientifiques (base de connaissance) :
{cases}

Propose au plus 3 mesures de défense contre la NOUVELLE attaque, en respectant
STRICTEMENT ces règles :
1. Chaque mesure part de la mitigation d'un cas ci-dessus et cite son
   identifiant dans "cited_cases". N'invente aucune défense absente des cas.
   Un cas marqué "aucune mitigation" ne peut pas être cité.
2. ADAPTE la mitigation à la nouvelle attaque : nomme ce qu'elle protège dans
   CETTE attaque (son vecteur, son mécanisme ou son impact), au lieu de
   recopier le texte du cas.
3. "broken_link" indique le maillon de la chaîne ci-dessus que la mesure casse :
   "input_vector", "bypass_mechanism" ou "impact". Si la mitigation ne casse
   aucun maillon de CETTE attaque, mets "none" : elle ne s'applique pas.
4. Si aucun cas ne s'applique, renvoie une liste vide.

Réponds UNIQUEMENT avec un objet JSON, sans texte autour :
{{
  "recommendations": [
    {{
      "action": "<mesure adaptée, 1 phrase, en anglais>",
      "broken_link": "<input_vector | bypass_mechanism | impact | none>",
      "mitigation_type": "<un des types ci-dessous, ou null>",
      "cited_cases": ["C1"]
    }}
  ]
}}

Types de mitigation autorisés :
{types}"""

PROMPT_REVISE_CAUSAL = """Tu es un analyste en sécurité des systèmes d'IA.

Nouvelle attaque signalée :
"{attack}"

Sa chaîne causale :
- input_vector : {input_vector}
- bypass_mechanism : {bypass_mechanism}
- impact : {impact}

Cas similaires extraits d'articles scientifiques :
{cases}

Un vérificateur a REJETÉ les mesures suivantes :
{rejected}

Pour chaque mesure rejetée, soit tu la réécris pour qu'elle reste fidèle à la
mitigation du cas cité ET casse un maillon de la chaîne ci-dessus (en le
nommant), soit tu la retires. Ne renvoie QUE les mesures corrigées ; liste vide
si aucune ne peut l'être. Même format JSON que précédemment :
{{"recommendations": [{{"action": "...", "broken_link": "...", "mitigation_type": "...", "cited_cases": ["C1"]}}]}}
JSON :"""

PROMPT_JUDGE = """Tu es un vérificateur en sécurité des systèmes d'IA.

Nouvelle attaque :
"{attack}"
Chaîne causale : input_vector = {input_vector} ; bypass_mechanism = {bypass_mechanism} ; impact = {impact}

Mitigation du cas cité ({case_id}) :
"{mitigation}"

Mesure proposée :
"{action}"

La mesure est-elle (1) fidèle à la mitigation citée et (2) capable de casser un
maillon de la chaîne de la nouvelle attaque ? Réponds UNIQUEMENT avec un JSON :
{{"accept": true ou false, "broken_link": "<input_vector | bypass_mechanism | impact | none>", "reason": "<courte>"}}
JSON :"""


def format_chain(chain: dict) -> dict:
    return {k: (chain.get(k) or "inconnu") for k in LINKS}


def parse_chain(parsed: dict) -> dict:
    """Garde les trois maillons attendus ; tout le reste (ou une chaîne vide) devient None."""
    chain = {}
    for k in LINKS:
        v = parsed.get(k) if isinstance(parsed, dict) else None
        chain[k] = v.strip() if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none") else None
    return chain


def normalize_link(value) -> str | None:
    v = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in LINKS else ("none" if v in ("none", "aucun", "null", "") else None)


# --------------------------------------------------------------------------- #
# Verify
# --------------------------------------------------------------------------- #
def is_adapted(action: str, mitigation: str | None, attack: str, chain: dict) -> bool:
    """La recommandation nomme un élément de la nouvelle attaque absent de la mitigation citée."""
    query_words = _words(attack) | set().union(*(_words(v) for v in chain.values() if v))
    return bool((_words(action) & query_words) - _words(mitigation))


def verify_causal(recs: list[dict], cases: list[dict], attack: str, chain: dict, verifier: str,
                  embed, judge=None) -> list[dict]:
    """
    Annote chaque recommandation : traceable, reason, cited (index du cas
    retenu), semantic_support, broken_link (étiqueté ou déduit),
    link_similarity, causally_adequate, adapted.
    `embed(text) -> vecteur` (mis en cache par l'appelant) ; `judge(rec, case,
    case_id) -> dict` pour la variante "llm".
    """
    if verifier not in VERIFIERS:
        raise ValueError(f"Vérificateur inconnu : {verifier} (attendu : {VERIFIERS})")
    from remediation import _cited_indexes  # import local : évite l'import circulaire

    present_links = {k: v for k, v in chain.items() if v}
    out = []
    for rec in recs:
        action = (rec.get("action") or "").strip()
        a = {**rec, "broken_link_label": normalize_link(rec.get("broken_link"))}
        indexes = [i for i in _cited_indexes(rec.get("cited_cases")) if 0 <= i < len(cases)]
        with_mit = [i for i in indexes if cases[i].get("mitigation_summary")]

        # Support sémantique sur le meilleur cas cité
        best, support = None, 0.0
        if action:
            for i in with_mit:
                s = _cosine(embed(action), embed(cases[i]["mitigation_summary"]))
                if s > support:
                    best, support = i, s
        a["cited"] = best
        a["semantic_support"] = round(support, 3)

        # Maillon : déduit (rule) ou étiqueté (labels / llm)
        link_sims = {k: _cosine(embed(action), embed(v)) for k, v in present_links.items()} if action else {}
        if verifier == "rule":
            link = max(link_sims, key=link_sims.get, default=None)
            link = link if link and link_sims[link] >= LINK_MIN else "none"
        else:
            link = a["broken_link_label"]
        a["broken_link"] = link
        a["link_similarity"] = round(link_sims.get(link, 0.0), 3) if link in LINKS else 0.0
        a["causally_adequate"] = bool(link in present_links and a["link_similarity"] >= LINK_MIN)
        mitigation = cases[best]["mitigation_summary"] if best is not None else None
        a["adapted"] = bool(action) and is_adapted(action, mitigation, attack, chain)

        # Décision
        if not action:
            reason = "recommandation vide"
        elif not indexes:
            reason = "aucun cas cité"
        elif not with_mit:
            reason = "le(s) cas cité(s) ne porte(nt) aucune mitigation"
        elif verifier == "llm":
            verdict = judge(a, cases[best if best is not None else with_mit[0]],
                            f"C{(best if best is not None else with_mit[0]) + 1}")
            a["judge"] = verdict
            jl = normalize_link(verdict.get("broken_link"))
            if jl in LINKS:
                a["broken_link"] = jl
                a["link_similarity"] = round(link_sims.get(jl, 0.0), 3)
                a["causally_adequate"] = bool(jl in present_links and a["link_similarity"] >= LINK_MIN)
            reason = None if verdict.get("accept") is True else f"rejet du juge LLM : {verdict.get('reason') or 'sans raison'}"
        elif support < SEMANTIC_MIN:
            reason = f"mitigation citée trop éloignée sémantiquement ({support:.2f} < {SEMANTIC_MIN})"
        elif link == "none":
            reason = "ne casse aucun maillon de la nouvelle attaque"
        elif link is None:
            reason = f"maillon non reconnu : {rec.get('broken_link')!r}"
        elif link not in present_links:
            reason = f"le maillon {link} n'existe pas dans la chaîne de cette attaque"
        elif a["link_similarity"] < LINK_MIN:
            reason = (f"la mesure ne parle pas du maillon {link} "
                      f"({a['link_similarity']:.2f} < {LINK_MIN})")
        else:
            reason = None

        if reason is None and best is not None:
            a["proposed_type"] = rec.get("mitigation_type")
            a["mitigation_type"] = cases[best].get("mitigation_type")
        a["traceable"] = reason is None
        a["reason"] = reason
        out.append(a)
    return out


def rate(final: list[dict], key: str) -> float | None:
    return round(sum(bool(r.get(key)) for r in final) / len(final), 3) if final else None
