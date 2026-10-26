"""OCR and extraction quality metrics (no external dependencies).

CER = character error rate, WER = word error rate. Both are
edit_distance(reference, hypothesis) / len(reference).
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence


def edit_distance(a: Sequence, b: Sequence) -> int:
    """Levenshtein distance using two rolling rows (O(min(n, m)) memory)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            cost = 0 if item_a == item_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = _normalise(reference), _normalise(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = _normalise(reference).split(), _normalise(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def _best_substring_distance(reference: Sequence, text: Sequence) -> int:
    """Smallest edit distance between `reference` and ANY substring of `text`
    (Sellers' algorithm: free start/end in `text`). Order-independent, so a
    two-column page can be scored line by line."""
    previous = list(range(len(reference) + 1))
    best = previous[-1]
    for item in text:
        current = [0]  # a match may start anywhere in `text`
        for j, ref_item in enumerate(reference, start=1):
            cost = 0 if ref_item == item else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        best = min(best, current[-1])
        previous = current
    return best


def line_cer(reference_lines: Sequence[str], hypothesis: str) -> float:
    """CER of known reference lines against the OCR text of the whole page."""
    hyp = _normalise(hypothesis)
    refs = [_normalise(r) for r in reference_lines if r.strip()]
    total = sum(len(r) for r in refs)
    if not total:
        return 0.0
    return sum(_best_substring_distance(r, hyp) for r in refs) / total


def line_wer(reference_lines: Sequence[str], hypothesis: str) -> float:
    """WER of known reference lines against the OCR text of the whole page."""
    hyp = _normalise(hypothesis).split()
    refs = [_normalise(r).split() for r in reference_lines if r.strip()]
    total = sum(len(r) for r in refs)
    if not total:
        return 0.0
    return sum(_best_substring_distance(r, hyp) for r in refs) / total


def field_accuracy(expected: Mapping[str, object], predicted: Mapping[str, object]) -> dict:
    """Exact-match accuracy per field plus an overall score.

    Strings are compared case-insensitively; floats within 0.01.
    """
    per_field: dict[str, bool] = {}
    for key, want in expected.items():
        got = predicted.get(key)
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            per_field[key] = abs(float(want) - float(got)) <= 0.01
        else:
            per_field[key] = str(want).strip().lower() == str(got).strip().lower() if got is not None else False
    total = len(per_field)
    correct = sum(per_field.values())
    return {
        "per_field": per_field,
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
    }
