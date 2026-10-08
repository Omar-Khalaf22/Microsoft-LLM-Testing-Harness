"""Lina's configurable objective scorer, executed only on the backend."""

from __future__ import annotations

import re
from math import floor

from .models import CriterionResult
from .weights import ScoringWeights, default_weights

STOP_WORDS = set(
    (
        "the and for with what why how from into this that explain describe "
        "write provide tell are is to of in on a an"
    ).split()
)


def _round_points(value: float) -> float:
    # Match JavaScript Math.round for the nonnegative scoring domain.
    return floor(value * 10 + 0.5) / 10


def score_response(
    prompt: str,
    response: str,
    keywords: list[str],
    minimum_length: int,
    minimum_sentences: int = 2,
    forbidden_terms: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> tuple[float, list[CriterionResult]]:
    points = ScoringWeights.model_validate(
        weights if weights is not None else default_weights()
    ).model_dump()
    normalized = response.lower()
    matches = [word for word in keywords if word.lower() in normalized]
    keyword_ratio = len(matches) / len(keywords) if keywords else 1
    prompt_terms = {
        word
        for word in re.findall(r"[a-z0-9']+", prompt.lower())
        if len(word) > 2 and word not in STOP_WORDS
    }
    response_terms = set(re.findall(r"[a-z0-9']+", normalized))
    relevant = len(prompt_terms & response_terms)
    relevance_ratio = relevant / len(prompt_terms) if prompt_terms else 1
    length_ratio = min(1, len(response) / minimum_length) if minimum_length else 1
    sentences = len([part for part in re.split(r"[.!?]+", response) if part.strip()])
    sentence_ratio = min(1, sentences / max(1, minimum_sentences))
    forbidden = [term for term in forbidden_terms or [] if term.lower() in normalized]
    valid = bool(response.strip())
    criteria = [
        CriterionResult(
            "Keyword coverage",
            keyword_ratio == 1,
            _round_points(keyword_ratio * points["keyword"]),
            f"Matched {len(matches)} of {len(keywords)} keywords"
            if keywords
            else "No required keywords configured",
        ),
        CriterionResult(
            "Prompt relevance",
            relevance_ratio >= 0.5,
            _round_points(min(1, relevance_ratio) * points["relevance"]),
            f"Matched {relevant} of {len(prompt_terms)} meaningful prompt terms",
        ),
        CriterionResult(
            "Minimum length",
            len(response) >= minimum_length,
            _round_points(length_ratio * points["length"]),
            f"Response contains {len(response)} characters; target is {minimum_length}",
        ),
        CriterionResult(
            "Sentence structure",
            sentences >= minimum_sentences,
            _round_points(sentence_ratio * points["sentences"]),
            f"Response contains {sentences} sentences; target is {minimum_sentences}",
        ),
        CriterionResult(
            "Forbidden terms",
            not forbidden,
            points["forbidden"] if not forbidden else 0,
            "No forbidden terms detected" if not forbidden else f"Detected: {', '.join(forbidden)}",
        ),
        CriterionResult(
            "Valid response",
            valid,
            points["valid"] if valid else 0,
            "Model returned usable text" if valid else "Response is empty",
        ),
    ]
    return min(100, _round_points(sum(item.score for item in criteria))), criteria
