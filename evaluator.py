"""
evaluator.py
------------
Évaluation quantitative des deux pipelines (GLiNER vs Mistral prompt-based)
par rapport à un ground truth annoté manuellement.

Métriques calculées :
  - Precision, Recall, F1-score (exact match ET fuzzy match sur le texte)
  - Taux d'hallucination : proportion d'entités extraites qui n'apparaissent
    PAS littéralement dans le texte source (signal fort d'invention du LLM)
  - Comparaison finale entre méthodes pour un même PDF

Usage typique : voir main.py
"""

import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher


def _normalize(s: str) -> str:
    return s.strip().lower()


def _fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    """Match approximatif pour tolérer les petites variations de tokenisation."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() >= threshold


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
        }


def compute_hallucination_rate(
    predicted_entities: list[dict], source_text: str
) -> tuple[float, list]:
    """
    Une entité est jugée "hallucinée" si son texte n'apparaît pas (même
    approximativement) dans le document source. C'est le signal le plus
    direct et le plus objectif d'hallucination pour de l'extraction.
    """
    if not predicted_entities:
        return 0.0, []

    normalized_source = _normalize(source_text)
    hallucinated = []

    for e in predicted_entities:
        text = e.get("text", "")
        if not text:
            continue
        if _normalize(text) not in normalized_source:
            hallucinated.append(text)

    rate = len(hallucinated) / len(predicted_entities)
    return rate, hallucinated


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
    gt_matched = [False] * len(ground_truth_entities)
    tp = 0
    fp = 0

    for pred in predicted_entities:
        pred_text = pred.get("text", "")
        match_found = False
        for i, gt in enumerate(ground_truth_entities):
            if gt_matched[i]:
                continue
            same_text = (
                _fuzzy_match(pred_text, gt["text"])
                if fuzzy
                else _normalize(pred_text) == _normalize(gt["text"])
            )
            if same_text:
                gt_matched[i] = True
                match_found = True
                tp += 1
                break
        if not match_found:
            fp += 1

    fn = gt_matched.count(False)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

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
