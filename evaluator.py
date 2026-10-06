"""
evaluator.py
------------
Évaluation quantitative des deux pipelines (GLiNER vs Mistral prompt-based)
par rapport à un ground truth annoté manuellement.

Métriques calculées :
  - Precision, Recall, F1-score (exact match ET fuzzy match sur le texte),
    en version STRICTE (métrique principale) et RELÂCHÉE (inclusion d'un
    span dans l'autre, rapportée à côté, jamais à la place)
  - Taux d'hallucination : proportion d'entités extraites qui n'apparaissent
    PAS littéralement dans le texte source (signal fort d'invention du LLM)
  - Comparaison finale entre méthodes pour un même PDF

Usage typique : voir main.py
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Tirets typographiques et apostrophes courbes produits par l'extraction PDF :
# "LLM‑integrated" (tiret insécable) ou "You’ve" ne doivent pas différer de
# leur forme ASCII — ce sont les mêmes mots.
_DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"})
_QUOTES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})
_EDGE_PUNCT = " \t\n.,;:!?\"'()[]{}«»"
_LEADING_ARTICLE = re.compile(r"^(?:the|a|an|le|la|les|un|une|des)\s+")

# Seuil de la correspondance relâchée : le span le plus court doit couvrir au
# moins cette part des mots du plus long ("GPT-4 model" / "GPT-4" : 1/2).
RELAXED_MIN_COVERAGE = 0.5


def _normalize(s: str) -> str:
    """
    Forme canonique d'un texte pour la comparaison : Unicode NFKC, minuscules,
    tirets et apostrophes unifiés, espaces (y compris sauts de ligne)
    compactés, ponctuation de bord et article initial retirés.

    Avant : strip().lower() seulement. Deux effets injustes en découlaient.
    (1) Une entité coupée par un saut de ligne dans le texte extrait (fin de
    ligne au milieu d'un nom en deux mots) n'était jamais retrouvée
    "littéralement" dans la source et comptait comme HALLUCINATION alors
    qu'elle y figure bien. (2) "Github Copilot," (virgule collée) ou
    "Zero‑Width‑Joiner" (tirets Unicode) comptaient comme hallucinés ET comme
    faux positifs alors que c'est exactement l'entité annotée.
    """
    s = unicodedata.normalize("NFKC", s).translate(_DASHES).translate(_QUOTES)
    s = re.sub(r"\s+", " ", s.lower()).strip(_EDGE_PUNCT)
    return _LEADING_ARTICLE.sub("", s)


def _relaxed_match(a: str, b: str) -> bool:
    """
    Correspondance relâchée (au sens des évaluations NER "partial match") :
    l'un des deux spans est contenu dans l'autre, mot pour mot, et couvre au
    moins RELAXED_MIN_COVERAGE de ses mots. "Bing Chat sidebar" retrouve
    "Bing Chat" (2/3) ; "LLM" ne retrouve pas "LLM-integrated applications"
    ("llm-integrated" est un autre mot) mais retrouve "LLM supervisor" (1/2) :
    c'est une métrique volontairement permissive, rapportée À CÔTÉ de la
    stricte pour montrer la part des écarts due aux seules frontières de span.
    """
    wa, wb = _normalize(a).split(), _normalize(b).split()
    if not wa or not wb:
        return False
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    n = len(short)
    contained = any(long_[i : i + n] == short for i in range(len(long_) - n + 1))
    return contained and n / len(long_) >= RELAXED_MIN_COVERAGE


def _dedupe_by_text(entities: list[dict]) -> list[dict]:
    """
    Une prédiction par texte. L'appariement ignore le label : le même texte
    extrait sous deux labels différents ("Bing Chat" en application ET en
    vecteur d'entrée) comptait une fois vrai positif, une fois faux positif —
    une pénalité pour une information pourtant correcte.
    """
    seen, unique = set(), []
    for e in entities:
        key = _normalize(e.get("text", ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def _fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    """Match approximatif pour tolérer les petites variations de tokenisation."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() >= threshold


def _fuzzy_contains(needle: str, haystack: str, threshold: float) -> bool:
    """
    Cherche needle dans haystack de façon approximative. Comparer needle à des
    fenêtres de haystack de longueur fixe dilue le ratio dès que la fenêtre
    déborde un peu du contenu réel (le "padding" compte comme non-matché) :
    on ancre donc la comparaison sur le plus long segment commun entre needle
    et haystack (find_longest_match), puis on extrait de haystack la portion
    de MÊME longueur que needle alignée sur cet ancrage, avant de comparer les
    deux avec le même ratio (0.85) que celui utilisé pour le F1 dans evaluate().
    """
    sm = SequenceMatcher(None, needle, haystack, autojunk=False)
    anchor = sm.find_longest_match(0, len(needle), 0, len(haystack))
    if anchor.size == 0:
        return False
    start = max(anchor.b - anchor.a, 0)
    candidate = haystack[start : start + len(needle)]
    return _fuzzy_match(needle, candidate, threshold)


@dataclass
class EvalResult:
    method: str
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    hallucination_rate: float  # % d'entités absentes du texte source
    hallucinated_entities: list = field(default_factory=list)
    n_predicted: int = 0
    n_ground_truth: int = 0
    relaxed_precision: float = 0.0
    relaxed_recall: float = 0.0
    relaxed_f1: float = 0.0
    n_predicted_raw: int = 0

    def to_dict(self):
        return {
            "method": self.method,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "hallucination_rate": round(self.hallucination_rate, 4),
            "hallucinated_entities": self.hallucinated_entities,
            "n_predicted": self.n_predicted,
            "n_ground_truth": self.n_ground_truth,
            "relaxed_precision": round(self.relaxed_precision, 4),
            "relaxed_recall": round(self.relaxed_recall, 4),
            "relaxed_f1": round(self.relaxed_f1, 4),
            "n_predicted_raw": self.n_predicted_raw,
        }


def compute_hallucination_rate(
    predicted_entities: list[dict], source_text: str, fuzzy_threshold: float = 0.85
) -> tuple[float, list]:
    """
    Une entité est jugée "hallucinée" si son texte n'apparaît pas dans le
    document source, ni littéralement, ni approximativement pour les textes
    longs. Le match exact reste la première vérification (rapide, sans faux
    négatif) ; pour les entités de plus de 20 caractères (ex: citations
    longues), on tolère en plus un fuzzy match (voir _fuzzy_contains), avec le
    même seuil (0.85) que celui utilisé pour le F1 dans evaluate() — sans ça,
    une citation légèrement déformée par l'extraction PDF (espaces, césures)
    était comptée comme hallucination ici alors qu'elle aurait compté comme
    vrai positif côté F1, ce qui est incohérent.
    """
    if not predicted_entities:
        return 0.0, []

    normalized_source = _normalize(source_text)
    hallucinated = []

    for e in predicted_entities:
        text = e.get("text", "")
        if not text:
            continue
        norm_text = _normalize(text)
        if norm_text in normalized_source:
            continue
        if len(norm_text) > 20 and _fuzzy_contains(
            norm_text, normalized_source, fuzzy_threshold
        ):
            continue
        hallucinated.append(text)

    rate = len(hallucinated) / len(predicted_entities)
    return rate, hallucinated


def greedy_match(predicted_entities: list[dict], ground_truth_entities: list[dict], *matchers):
    """
    Appariement glouton prédictions -> ground truth, chaque entité annotée ne
    pouvant être retrouvée qu'une fois. Les critères sont essayés dans l'ordre
    pour chaque prédiction : en relâché, une correspondance stricte est
    toujours préférée à une simple inclusion, pour qu'une inclusion ne "vole"
    pas une entité qu'une autre prédiction retrouve exactement.
    Renvoie (prédiction appariée ?, entité annotée retrouvée ?).
    """
    gt_matched = [False] * len(ground_truth_entities)
    pred_matched = []
    for pred in predicted_entities:
        pred_text = pred.get("text", "")
        hit = next(
            (
                i
                for matches in matchers
                for i, gt in enumerate(ground_truth_entities)
                if not gt_matched[i] and matches(pred_text, gt["text"])
            ),
            None,
        )
        if hit is not None:
            gt_matched[hit] = True
        pred_matched.append(hit is not None)
    return pred_matched, gt_matched


def strict_matcher(fuzzy: bool = True):
    """Critère strict du F1 : fuzzy match (0.85) sur les textes normalisés."""
    return (lambda a, b: _fuzzy_match(a, b)) if fuzzy else (lambda a, b: _normalize(a) == _normalize(b))


def false_positive_entities(predicted_entities: list[dict], ground_truth_entities: list[dict],
                            fuzzy: bool = True) -> list[dict]:
    """Prédictions comptées faux positifs par le F1 strict (après dédoublonnage par texte)."""
    preds = _dedupe_by_text(predicted_entities)
    matched, _ = greedy_match(preds, ground_truth_entities, strict_matcher(fuzzy))
    return [p for p, m in zip(preds, matched) if not m]


def evaluate(
    method_name: str,
    predicted_entities: list[dict],
    ground_truth_entities: list[dict],
    source_text: str,
    fuzzy: bool = True,
) -> EvalResult:
    """
    Compare une liste d'entités prédites à un ground truth annoté.
    ground_truth_entities format attendu : [{"text": "...", "label": "..."}]
    """
    n_raw = len(predicted_entities)
    predicted_entities = _dedupe_by_text(predicted_entities)

    def score(*matchers) -> tuple[int, int, int, float, float, float]:
        pred_matched, gt_matched = greedy_match(predicted_entities, ground_truth_entities, *matchers)
        tp = sum(pred_matched)
        fp = len(pred_matched) - tp
        fn = gt_matched.count(False)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return tp, fp, fn, p, r, f

    strict = strict_matcher(fuzzy)

    tp, fp, fn, precision, recall, f1 = score(strict)
    _, _, _, r_precision, r_recall, r_f1 = score(strict, _relaxed_match)

    halluc_rate, halluc_list = compute_hallucination_rate(
        predicted_entities, source_text
    )

    return EvalResult(
        method=method_name,
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        hallucination_rate=halluc_rate,
        hallucinated_entities=halluc_list,
        n_predicted=len(predicted_entities),
        n_ground_truth=len(ground_truth_entities),
        relaxed_precision=r_precision,
        relaxed_recall=r_recall,
        relaxed_f1=r_f1,
        n_predicted_raw=n_raw,
    )


def compare_methods(results: list[EvalResult]) -> dict:
    """
    Classe les méthodes par F1 décroissant, puis par taux d'hallucination
    croissant en cas d'égalité. Renvoie le récapitulatif + le "gagnant".
    """
    ranked = sorted(results, key=lambda r: (-r.f1, r.hallucination_rate))
    best = ranked[0]

    return {
        "ranking": [r.to_dict() for r in ranked],
        "best_method": best.method,
        "summary": (
            f"{best.method} obtient le meilleur compromis : "
            f"F1={best.f1:.3f}, hallucination={best.hallucination_rate:.1%}"
        ),
    }


if __name__ == "__main__":
    # Exemple d'utilisation autonome
    text = "L'attaquant a utilisé l'IP 185.220.101.5 pour exploiter CVE-2023-23397."
    ground_truth = [
        {"text": "185.220.101.5", "label": "adresse IP"},
        {"text": "CVE-2023-23397", "label": "identifiant CVE"},
    ]
    predicted = [
        {"text": "185.220.101.5", "label": "adresse IP"},
        {"text": "CVE-2023-23397", "label": "identifiant CVE"},
        {"text": "APT29", "label": "acteur de menace"},  # halluciné : absent du texte
    ]
    result = evaluate("demo_method", predicted, ground_truth, text)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
