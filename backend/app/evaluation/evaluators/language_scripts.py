"""Bounded Unicode script evidence for response language checks.

This checks script compatibility, not full natural language identification.
"""

import unicodedata

SCRIPTS = {
    "ar": ("ARABIC",),
    "ru": ("CYRILLIC",),
    "el": ("GREEK",),
    "he": ("HEBREW",),
    "hi": ("DEVANAGARI",),
    "ko": ("HANGUL",),
    "ja": ("HIRAGANA", "KATAKANA", "CJK UNIFIED"),
    "zh": ("CJK UNIFIED",),
}
SCRIPT_NAMES = tuple(dict.fromkeys(part for values in SCRIPTS.values() for part in values))


def _script_counts(response: str) -> tuple[dict[str, int], int]:
    counts = {language: 0 for language in SCRIPTS}
    letters = 0
    for character in response:
        if not character.isalpha():
            continue
        letters += 1
        name = unicodedata.name(character, "")
        for language, names in SCRIPTS.items():
            if any(part in name for part in names):
                counts[language] += 1
    return counts, letters


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"language_detection", "response_language"}:
        raise ValueError("Unknown language criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    language = parameters["expected_language"]
    counts, letters = _script_counts(response)
    if not letters:
        raise ValueError("Cannot determine language from text without letters")
    if language == "en":
        latin = sum(
            character.isalpha() and "LATIN" in unicodedata.name(character, "")
            for character in response
        )
        score = latin / letters
        detail = f"Latin script evidence: {latin}/{letters}"
    else:
        matched = counts[language]
        score = matched / letters
        detail = f"{language} script evidence: {matched}/{letters}"
    passed = score >= parameters["minimum_script_fraction"]
    return passed, score, detail
