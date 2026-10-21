"""Automated response scoring."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from .models import CriterionResult

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "describe",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "list",
    "of",
    "on",
    "or",
    "provide",
    "tell",
    "the",
    "to",
    "what",
    "when",
    "where",
    "why",
    "with",
    "write",
}


def score_response(
    prompt: str,
    response: str,
    keywords: list[str],
    minimum_length: int,
    minimum_sentences: int = 2,
    forbidden_terms: list[str] | None = None,
    weights: dict[str, int] | None = None,
) -> tuple[float, list[CriterionResult]]:
    """Score one model response against configured objective criteria."""
    criteria: list[CriterionResult] = []
    weights = weights or {
        "keywords": 30,
        "relevance": 20,
        "length": 15,
        "sentences": 15,
        "forbidden": 10,
        "nonempty": 10,
    }
    if set(weights) != {"keywords", "relevance", "length", "sentences", "forbidden", "nonempty"}:
        raise ValueError("Scoring weights must contain all six criteria")
    if any(type(value) is not int or value < 0 for value in weights.values()):
        raise ValueError("Scoring weights must be nonnegative integers")
    if sum(weights.values()) != 100:
        raise ValueError("Scoring weights must total 100")
    def points(key: str, fraction: float) -> float:
        amount = Decimal(weights[key]) * Decimal(str(fraction))
        return float(amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    normalized = response.casefold()
    forbidden_terms = forbidden_terms or []

    if keywords:
        matches = [keyword for keyword in keywords if keyword.casefold() in normalized]
        keyword_score = points("keywords", len(matches) / len(keywords))
        missing = [keyword for keyword in keywords if keyword not in matches]
        detail = f"Matched {len(matches)} of {len(keywords)} keywords"
        if missing:
            detail += f". Missing: {', '.join(missing)}"
        criteria.append(
            CriterionResult(
                "Keyword coverage",
                len(matches) == len(keywords),
                round(keyword_score, 1),
                detail,
            )
        )
    else:
        keyword_score = weights["keywords"]
        criteria.append(
            CriterionResult(
                "Keyword coverage",
                True,
                weights["keywords"],
                "No required keywords were configured",
            )
        )

    prompt_terms = {
        word.casefold()
        for word in re.findall(r"[A-Za-z0-9']+", prompt)
        if len(word) > 2 and word.casefold() not in STOP_WORDS
    }
    response_terms = {word.casefold() for word in re.findall(r"[A-Za-z0-9']+", response)}
    relevant_matches = prompt_terms & response_terms
    relevance_ratio = len(relevant_matches) / max(len(prompt_terms), 1)
    relevance_score = points("relevance", min(1, relevance_ratio))
    criteria.append(
        CriterionResult(
            "Prompt relevance",
            relevance_ratio >= 0.5,
            round(relevance_score, 1),
            f"Matched {len(relevant_matches)} of {len(prompt_terms)} meaningful prompt terms",
        )
    )

    length_passed = len(response) >= minimum_length
    length_score = points("length", min(1, len(response) / max(minimum_length, 1)))
    criteria.append(
        CriterionResult(
            "Minimum length",
            length_passed,
            round(length_score, 1),
            f"Response contains {len(response)} characters; target is {minimum_length}",
        )
    )

    sentences = [part for part in re.split(r"[.!?]+", response) if part.strip()]
    structure_passed = len(sentences) >= minimum_sentences
    structure_score = points("sentences", min(1, len(sentences) / minimum_sentences))
    criteria.append(
        CriterionResult(
            "Sentence structure",
            structure_passed,
            round(structure_score, 1),
            f"Response contains {len(sentences)} sentences; target is {minimum_sentences}",
        )
    )

    found_forbidden = [term for term in forbidden_terms if term.casefold() in normalized]
    safety_passed = not found_forbidden
    safety_detail = (
        "No forbidden terms detected"
        if safety_passed
        else f"Detected: {', '.join(found_forbidden)}"
    )
    criteria.append(
        CriterionResult("Forbidden terms", safety_passed, weights["forbidden"] if safety_passed else 0, safety_detail)
    )

    nonempty_passed = bool(response.strip())
    validity_detail = "Model returned usable text" if nonempty_passed else "Response is empty"
    criteria.append(
        CriterionResult(
            "Valid response",
            nonempty_passed,
            weights["nonempty"] if nonempty_passed else 0,
            validity_detail,
        )
    )

    total = round(
        keyword_score
        + relevance_score
        + length_score
        + structure_score
        + (10 if safety_passed else 0)
        + (10 if nonempty_passed else 0),
        1,
    )
    return min(total, 100), criteria
