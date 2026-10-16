"""Text normalization and the metrics that compare a transcript with ground truth."""

import re
from collections import Counter

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from harness.dataset import Checkbox, Edge

MATCH_RATIO = 80
SCAFFOLDING_LINES = {"## Diagram", "Edges:"}


def normalize(md: str) -> str:
    lines = [
        line for line in md.splitlines()
        if not (line.lstrip().startswith("#") and "(untitled)" in line)
        and line.strip() not in SCAFFOLDING_LINES
    ]
    s = "\n".join(lines)
    s = s.replace(", labelled", " ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[ xX]\]", " ", s)
    s = re.sub(r"→|->|=>", " ", s)
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def word_scores(ref: str, hyp: str) -> tuple[float, float, float]:
    ref_words, hyp_words = ref.split(), hyp.split()
    if not hyp_words or not ref_words:
        return 0.0, 0.0, 0.0
    common = sum((Counter(ref_words) & Counter(hyp_words)).values())
    precision, recall = common / len(hyp_words), common / len(ref_words)
    f1 = 2 * precision * recall / (precision + recall) if common else 0.0
    return precision, recall, f1


def cer(ref: str, hyp: str) -> float:
    return Levenshtein.distance(ref, hyp) / len(ref)


def hallucination_rate(ref: str, hyp: str) -> float:
    hyp_words = hyp.split()
    if not hyp_words:
        return 0.0
    vocab = set(ref.split())
    return sum(w not in vocab for w in hyp_words) / len(hyp_words)


def _close(a: str, b: str) -> bool:
    return fuzz.ratio(normalize(a), normalize(b)) >= MATCH_RATIO


def _edge_matches(ref: Edge, hyp: Edge) -> bool:
    if not (_close(ref.src, hyp.src) and _close(ref.dst, hyp.dst)):
        return False
    return ref.label is None or (hyp.label is not None and _close(ref.label, hyp.label))


def edge_scores(ref: list[Edge], hyp: list[Edge]) -> tuple[float | None, float | None]:
    if not ref:
        return None, None
    unmatched = list(hyp)
    matched = 0
    for r in ref:
        for h in unmatched:
            if _edge_matches(r, h):
                unmatched.remove(h)
                matched += 1
                break
    precision = matched / len(hyp) if hyp else 0.0
    return precision, matched / len(ref)


def checkbox_accuracy(ref: list[Checkbox], hyp: list[Checkbox]) -> float | None:
    if not ref:
        return None
    correct = 0
    for r in ref:
        best = max(hyp, key=lambda h: fuzz.ratio(normalize(r.text), normalize(h.text)), default=None)
        if best and _close(r.text, best.text) and best.checked == r.checked:
            correct += 1
    return correct / len(ref)
