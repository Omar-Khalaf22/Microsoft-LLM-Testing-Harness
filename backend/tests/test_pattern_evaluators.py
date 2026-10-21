"""Tests for the pattern, format, numeric, word-count and section evaluators."""

import time

import pytest

from app.evaluation.evaluators import patterns
from app.evaluation.evaluators.patterns import (
    EVALUATORS,
    PARAMETER_SCHEMAS,
    EvaluatorResult,
    ParameterError,
    email_format,
    numeric_exact,
    numeric_range,
    numeric_tolerance,
    regex_match,
    regex_not_match,
    required_sections,
    url_format,
    validate_parameters,
    word_count_max,
    word_count_min,
)

EXPECTED_IDS = {
    "regex_match",
    "regex_not_match",
    "email_format",
    "url_format",
    "numeric_exact",
    "numeric_range",
    "numeric_tolerance",
    "word_count_min",
    "word_count_max",
    "required_sections",
}


def passed(result: EvaluatorResult) -> bool:
    assert isinstance(result, EvaluatorResult)
    assert result.score == (1.0 if result.passed else 0.0)
    assert result.detail
    return result.passed


# ---------------------------------------------------------------------------------------------
# Registry and interface
# ---------------------------------------------------------------------------------------------


def test_exactly_the_ten_assigned_evaluators_are_exported():
    assert set(EVALUATORS) == EXPECTED_IDS
    assert set(PARAMETER_SCHEMAS) == EXPECTED_IDS


@pytest.mark.parametrize("criterion_id", sorted(EXPECTED_IDS))
def test_every_evaluator_has_a_complete_parameter_schema(criterion_id):
    schema = PARAMETER_SCHEMAS[criterion_id]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) <= set(schema["properties"])
    for spec in schema["properties"].values():
        assert spec["type"] in {"string", "boolean", "number", "integer", "array"}
        assert spec["description"]


@pytest.mark.parametrize("criterion_id", sorted(EXPECTED_IDS))
def test_evaluators_accept_the_shared_three_argument_interface(criterion_id):
    parameters = {
        "regex_match": {"pattern": "a"},
        "regex_not_match": {"pattern": "zzz"},
        "email_format": {},
        "url_format": {},
        "numeric_exact": {"expected": 1},
        "numeric_range": {"minimum": 0},
        "numeric_tolerance": {"expected": 1, "tolerance": 0.5},
        "word_count_min": {"minimum": 1},
        "word_count_max": {"maximum": 5},
        "required_sections": {"sections": ["Summary"]},
    }[criterion_id]
    result = EVALUATORS[criterion_id]("a 1", parameters, {"prompt": "ignored"})
    assert isinstance(result, EvaluatorResult)
    assert result.score in (0.0, 1.0)
    assert EVALUATORS[criterion_id].__name__ == criterion_id


def test_validate_parameters_applies_defaults_and_rejects_unknown_ids():
    resolved = validate_parameters("regex_match", {"pattern": "a"})
    assert resolved == {"pattern": "a", "ignore_case": False, "multiline": False, "dotall": False}
    with pytest.raises(ParameterError, match="Unknown pattern criterion"):
        validate_parameters("not_a_criterion", {})


# ---------------------------------------------------------------------------------------------
# regex_match / regex_not_match
# ---------------------------------------------------------------------------------------------


def test_regex_match_finds_pattern_anywhere():
    assert passed(regex_match("Order 12345 shipped", {"pattern": r"\d{5}"}))
    assert not passed(regex_match("Order shipped", {"pattern": r"\d{5}"}))


def test_regex_match_reports_matched_text_and_position():
    result = regex_match("abc 42 def", {"pattern": r"\d+"})
    assert "'42'" in result.detail and "position 4" in result.detail


def test_regex_flags_change_behavior():
    assert not passed(regex_match("HELLO", {"pattern": "hello"}))
    assert passed(regex_match("HELLO", {"pattern": "hello", "ignore_case": True}))
    assert not passed(regex_match("a\nb", {"pattern": "^b"}))
    assert passed(regex_match("a\nb", {"pattern": "^b", "multiline": True}))
    assert not passed(regex_match("a\nb", {"pattern": "a.b"}))
    assert passed(regex_match("a\nb", {"pattern": "a.b", "dotall": True}))


def test_regex_not_match_inverts_the_check():
    assert passed(regex_not_match("all good here", {"pattern": r"password\s*=\s*\S+"}))
    result = regex_not_match("password = hunter2", {"pattern": r"password\s*=\s*\S+"})
    assert not passed(result)
    assert "Forbidden pattern found" in result.detail


def test_regex_handles_unicode_and_empty_responses():
    assert passed(regex_match("caf\u00e9 \u2603", {"pattern": "\u2603"}))
    assert not passed(regex_match("", {"pattern": "a"}))
    assert passed(regex_not_match("", {"pattern": "a"}))


@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        ("(", "Invalid regular expression"),
        ("[a-", "Invalid regular expression"),
        ("   ", "must not be blank"),
        ("(a+)+$", "Nested quantifiers"),
        ("(a*)*", "Nested quantifiers"),
        ("(\\w+\\s?)*", "Nested quantifiers"),
        ("(ab?){2,}", "Nested quantifiers"),
        ("(?:a|aa)+", "Alternation inside a repeated group"),
        ("(a)\\1", "backreferences"),
        ("(?P<x>a)(?P=x)", "backreferences"),
        ("a{1,5000}", "Repeat counts above"),
        ("a" * 301, "at most 300 characters"),
    ],
)
def test_unsafe_or_invalid_patterns_are_rejected_before_execution(pattern, message):
    for evaluator in (regex_match, regex_not_match):
        with pytest.raises(ParameterError, match=message):
            evaluator("anything", {"pattern": pattern})
    with pytest.raises(ParameterError):
        validate_parameters("regex_match", {"pattern": pattern})


@pytest.mark.parametrize(
    "pattern",
    [r"^(Yes|No)\b", r"\$\d+(\.\d+)?", r"\b\d{4}-\d{2}-\d{2}\b", r"(?:foo|bar)", r"(?:ab){3}"],
)
def test_ordinary_patterns_are_accepted(pattern):
    assert validate_parameters("regex_match", {"pattern": pattern})["pattern"] == pattern


def test_runaway_pattern_is_stopped_by_the_time_limit(monkeypatch):
    # `.*.*x` is allowed statically but takes minutes on this input with Python's re engine.
    monkeypatch.setattr(patterns, "REGEX_TIMEOUT_SECONDS", 0.5)
    started = time.perf_counter()
    result = regex_match("a" * 8000, {"pattern": ".*.*x"})
    elapsed = time.perf_counter() - started
    assert not passed(result)
    assert "did not finish" in result.detail
    assert elapsed < 5


def test_unverifiable_regex_not_match_fails_instead_of_passing(monkeypatch):
    monkeypatch.setattr(patterns, "REGEX_TIMEOUT_SECONDS", 0.5)
    result = regex_not_match("a" * 8000, {"pattern": ".*.*x"})
    assert not passed(result)
    assert "could not be evaluated" in result.detail


def test_worker_failure_is_reported_as_failure(monkeypatch):
    def broken(*_args, **_kwargs):
        raise patterns._RegexWorkerError("boom")

    monkeypatch.setattr(patterns, "_isolated_search", broken)
    assert not passed(regex_match("a", {"pattern": "a"}))
    assert not passed(regex_not_match("a", {"pattern": "b"}))


# ---------------------------------------------------------------------------------------------
# email_format
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "bob@example.com",
        "Contact me at first.last+tag@sub.example.co.uk.",
        "(reach alice_b@example.org)",
        "Email: <jo-hn@my-site.io>, thanks",
        "mailto:support@example.com",
        "Two: bad@@x and good@example.com",
    ],
)
def test_email_contains_mode_finds_valid_addresses(text):
    assert passed(email_format(text, {}))


@pytest.mark.parametrize(
    "text",
    [
        "no address here",
        "user@localhost",
        "user@example",
        "@example.com",
        "user@.com",
        "user@example..com",
        "user.@example.com",
        "user@-example.com",
        "user@example.c",
        "a@b@example.com",
        "user@" + "a" * 64 + ".com",
        "",
    ],
)
def test_email_contains_mode_rejects_malformed_addresses(text):
    assert not passed(email_format(text, {}))


def test_email_exact_mode_requires_the_whole_response():
    assert passed(email_format("  bob@example.com\n", {"mode": "exact"}))
    assert not passed(email_format("Mail bob@example.com", {"mode": "exact"}))
    assert not passed(email_format("bob@example.com bob@example.org", {"mode": "exact"}))


@pytest.mark.parametrize(
    "text",
    ["us er@example.com", ".user@example.com", "user..name@example.com", "bob@example.com."],
)
def test_email_exact_mode_is_strict_about_the_whole_response(text):
    assert not passed(email_format(text, {"mode": "exact"}))


def test_email_contains_mode_ignores_surrounding_punctuation_and_whitespace():
    # Leading dots and sentence punctuation are not part of an address.
    assert passed(email_format("us er@example.com", {}))
    assert passed(email_format("...see.user@example.com", {}))
    assert passed(email_format(".user@example.com", {}))


def test_email_rejects_invalid_mode():
    with pytest.raises(ParameterError, match="must be one of"):
        email_format("a@b.com", {"mode": "loose"})


# ---------------------------------------------------------------------------------------------
# url_format
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com",
        "See http://example.com/a/b?x=1&y=2#frag for details.",
        "(https://example.com/path)",
        "[docs](https://example.com/docs)",
        "http://localhost:8000/health",
        "http://127.0.0.1:5173/",
        "https://[2001:db8::1]/index",
        "HTTPS://EXAMPLE.COM",
        "Visit https://sub.example.co.uk/page, then reply.",
    ],
)
def test_url_contains_mode_finds_valid_urls(text):
    assert passed(url_format(text, {}))


@pytest.mark.parametrize(
    "text",
    [
        "example.com",
        "no url",
        "ftp://example.com/file",
        "http://",
        "http://.com",
        "http://-bad.com",
        "http://exa mple.com",
        "https://example",
        "http://example.com:99999",
        "http://example.com:0",
        "://example.com",
        "javascript://alert(1)",
        "",
    ],
)
def test_url_contains_mode_rejects_malformed_or_unaccepted_urls(text):
    assert not passed(url_format(text, {}))


def test_url_scheme_list_is_configurable():
    assert passed(url_format("ftp://example.com/file", {"schemes": ["ftp"]}))
    assert not passed(url_format("https://example.com", {"schemes": ["ftp"]}))


def test_url_exact_mode_requires_the_whole_response():
    assert passed(url_format(" https://example.com/x \n", {"mode": "exact"}))
    assert not passed(url_format("Go to https://example.com/x", {"mode": "exact"}))


@pytest.mark.parametrize("schemes", [[], ["HTTP"], ["ht tp"], ["a"] * 6, "https", [1]])
def test_url_rejects_invalid_scheme_parameters(schemes):
    with pytest.raises(ParameterError):
        url_format("https://example.com", {"schemes": schemes})


def test_url_scan_is_bounded_on_adversarial_input():
    text = "a://" * 50_000
    started = time.perf_counter()
    assert not passed(url_format(text, {}))
    assert time.perf_counter() - started < 5


# ---------------------------------------------------------------------------------------------
# numeric extraction policy
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42", 42),
        ("The answer is 42.", 42),
        ("Total: $1,234.50", 1234.5),
        ("It is -7 degrees", -7),
        ("About +3.5 units", 3.5),
        ("45% of users", 45),
        ("roughly 1.5e3 items", 1500),
        ("(42)", 42),
        ("**42**", 42),
        ("Result \u22125", -5),
        ("0.5", 0.5),
        (".5", 0.5),
        ("1,000,000", 1_000_000),
    ],
)
def test_single_number_is_extracted(text, expected):
    assert passed(numeric_exact(text, {"expected": expected}))


@pytest.mark.parametrize(
    "text",
    [
        "The answer is 3 or 4",
        "Between 10 and 20",
        "Step 1: 42",
        "1 2 3",
        "-1 and +1",
    ],
)
def test_several_numbers_are_ambiguous_and_never_guessed(text):
    # The expected value is present, so a first/last-number heuristic would wrongly pass.
    for expected in (1, 3, 4, 10, 42):
        result = numeric_exact(text, {"expected": expected})
        assert not result.passed
        assert "Ambiguous" in result.detail
        assert "marker" in result.detail


def test_ambiguous_result_lists_candidates_but_caps_the_list():
    result = numeric_exact("1 2 3 4 5 6 7 8", {"expected": 1})
    assert "found 8 numbers" in result.detail
    assert result.detail.count(",") < 12 and "..." in result.detail


@pytest.mark.parametrize("text", ["no digits at all", "", "forty-two", "abc123def", "v1.2.3"])
def test_missing_numbers_fail_explicitly(text):
    result = numeric_exact(text, {"expected": 1})
    assert not result.passed
    assert "No numeric value found" in result.detail


def test_non_numeric_digit_tokens_are_reported_not_silently_used():
    result = numeric_exact("Released on 2024-05-01", {"expected": 2024})
    assert not result.passed
    assert "ignored" in result.detail


def test_marker_selects_a_single_number_from_a_noisy_response():
    text = "Step 1: add 3 and 4.\nStep 2: double it.\nAnswer: 14"
    assert not numeric_exact(text, {"expected": 14}).passed
    assert passed(numeric_exact(text, {"expected": 14, "marker": "Answer:"}))
    assert passed(numeric_exact(text, {"expected": 14, "marker": "answer:"}))


def test_marker_uses_the_last_occurrence_and_only_its_line():
    text = "Answer: 7\nrechecking...\nAnswer: 9\nbased on 2 reasons"
    assert passed(numeric_exact(text, {"expected": 9, "marker": "Answer:"}))
    assert not numeric_exact(text, {"expected": 7, "marker": "Answer:"}).passed


def test_marker_failures_are_explicit():
    missing = numeric_exact("just 5", {"expected": 5, "marker": "Answer:"})
    assert not missing.passed and "was not found" in missing.detail
    crowded = numeric_exact("Answer: 5 or 6", {"expected": 5, "marker": "Answer:"})
    assert not crowded.passed and "Ambiguous" in crowded.detail
    empty = numeric_exact("Answer: unknown", {"expected": 5, "marker": "Answer:"})
    assert not empty.passed and "No numeric value found" in empty.detail


def test_float_expected_values_compare_without_binary_rounding_noise():
    assert passed(numeric_exact("0.3", {"expected": 0.3}))
    assert passed(numeric_exact("42.0", {"expected": 42}))
    assert not numeric_exact("42.01", {"expected": 42}).passed


# ---------------------------------------------------------------------------------------------
# numeric_exact / numeric_range / numeric_tolerance behavior and parameters
# ---------------------------------------------------------------------------------------------


def test_numeric_exact_pass_and_fail_details():
    assert "expected exactly 42" in numeric_exact("42", {"expected": 42}).detail
    failed = numeric_exact("41", {"expected": 42})
    assert not failed.passed and "Found 41" in failed.detail


def test_numeric_range_inclusive_and_exclusive_bounds():
    spec = {"minimum": 1, "maximum": 10}
    assert passed(numeric_range("5", spec))
    assert passed(numeric_range("1", spec))
    assert passed(numeric_range("10", spec))
    assert not numeric_range("0.99", spec).passed
    assert not numeric_range("10.01", spec).passed
    exclusive = {**spec, "inclusive": False}
    assert passed(numeric_range("5", exclusive))
    assert not numeric_range("1", exclusive).passed
    assert not numeric_range("10", exclusive).passed


def test_numeric_range_supports_one_sided_bounds():
    assert passed(numeric_range("1000", {"minimum": 0}))
    assert not numeric_range("-1", {"minimum": 0}).passed
    assert passed(numeric_range("-1000", {"maximum": 0}))
    assert not numeric_range("1", {"maximum": 0}).passed


def test_numeric_range_requires_a_bound_and_ordered_bounds():
    with pytest.raises(ParameterError, match="provide 'minimum'"):
        numeric_range("5", {})
    with pytest.raises(ParameterError, match="must not exceed"):
        numeric_range("5", {"minimum": 10, "maximum": 1})


def test_numeric_tolerance_absolute():
    spec = {"expected": 100, "tolerance": 2}
    assert passed(numeric_tolerance("101.5", spec))
    assert passed(numeric_tolerance("98", spec))
    assert not numeric_tolerance("102.01", spec).passed
    assert passed(numeric_tolerance("100", {"expected": 100, "tolerance": 0}))


def test_numeric_tolerance_relative():
    spec = {"expected": 200, "tolerance": 0.05, "relative": True}
    assert passed(numeric_tolerance("209", spec))
    assert not numeric_tolerance("211", spec).passed
    assert passed(numeric_tolerance("0", {"expected": 0, "tolerance": 0.5, "relative": True}))
    assert not numeric_tolerance("0.1", {"expected": 0, "tolerance": 0.5, "relative": True}).passed


def test_numeric_tolerance_respects_marker_and_ambiguity():
    assert not numeric_tolerance("approx 99 or 101", {"expected": 100, "tolerance": 5}).passed
    spec = {"expected": 100, "tolerance": 5, "marker": "Result:"}
    assert passed(numeric_tolerance("run 1 of 3\nResult: 99", spec))


@pytest.mark.parametrize(
    ("evaluator", "parameters"),
    [
        (numeric_exact, {}),
        (numeric_exact, {"expected": "5"}),
        (numeric_exact, {"expected": True}),
        (numeric_exact, {"expected": float("nan")}),
        (numeric_exact, {"expected": float("inf")}),
        (numeric_exact, {"expected": 5, "marker": "   "}),
        (numeric_exact, {"expected": 5, "marker": "x" * 101}),
        (numeric_exact, {"expected": 5, "extra": 1}),
        (numeric_tolerance, {"expected": 5}),
        (numeric_tolerance, {"expected": 5, "tolerance": -1}),
        (numeric_tolerance, {"expected": 5, "tolerance": "1"}),
        (numeric_tolerance, {"expected": 5, "tolerance": 1, "relative": "yes"}),
        (numeric_range, {"minimum": None, "maximum": None}),
        (numeric_range, {"minimum": "1"}),
    ],
)
def test_invalid_numeric_parameters_raise(evaluator, parameters):
    with pytest.raises(ParameterError):
        evaluator("5", parameters)


def test_very_large_exponent_tokens_do_not_crash():
    result = numeric_exact("1e999 and more", {"expected": 1})
    assert isinstance(result, EvaluatorResult)
    result = numeric_exact("9" * 70, {"expected": 1})
    assert not result.passed


# ---------------------------------------------------------------------------------------------
# word_count_min / word_count_max
# ---------------------------------------------------------------------------------------------


def test_word_count_min_boundaries():
    assert passed(word_count_min("one two three", {"minimum": 3}))
    assert not word_count_min("one two", {"minimum": 3}).passed
    assert passed(word_count_min("", {"minimum": 0}))
    assert "has 2 words" in word_count_min("one two", {"minimum": 3}).detail


def test_word_count_max_boundaries():
    assert passed(word_count_max("one two three", {"maximum": 3}))
    assert not word_count_max("one two three four", {"maximum": 3}).passed
    assert passed(word_count_max("", {"maximum": 0}))
    assert not word_count_max("word", {"maximum": 0}).passed


def test_word_counting_rules():
    # Punctuation-only tokens do not count; hyphenated words and numbers do.
    text = "well-known   fact \u2014 in 2024 !!!\n\nnew\tline"
    assert passed(word_count_min(text, {"minimum": 6}))
    assert passed(word_count_max(text, {"maximum": 6}))
    assert not word_count_min(text, {"minimum": 7}).passed


@pytest.mark.parametrize(
    ("evaluator", "parameters"),
    [
        (word_count_min, {}),
        (word_count_min, {"minimum": -1}),
        (word_count_min, {"minimum": 2.5}),
        (word_count_min, {"minimum": "3"}),
        (word_count_min, {"minimum": True}),
        (word_count_min, {"minimum": 10**9}),
        (word_count_max, {}),
        (word_count_max, {"maximum": -1}),
        (word_count_max, {"maximum": None}),
    ],
)
def test_invalid_word_count_parameters_raise(evaluator, parameters):
    with pytest.raises(ParameterError):
        evaluator("some words", parameters)


# ---------------------------------------------------------------------------------------------
# required_sections
# ---------------------------------------------------------------------------------------------

REPORT = """\
# Summary
The circuit works.

## Analysis:
Details here.

**Conclusion:** it is fine.

3. Recommendations
- Next Steps
Results: all green
"""


def test_required_sections_recognizes_headings_labels_and_list_items():
    sections = ["Summary", "Analysis", "Conclusion", "Recommendations", "Next Steps", "Results"]
    result = required_sections(REPORT, {"sections": sections})
    assert passed(result) and "All 6" in result.detail


def test_required_sections_reports_what_is_missing():
    result = required_sections(REPORT, {"sections": ["Summary", "Appendix", "References"]})
    assert not result.passed
    assert "Missing 2 of 3" in result.detail
    assert "Appendix" in result.detail and "References" in result.detail
    assert "Summary" not in result.detail


def test_required_sections_ignores_prose_and_partial_matches():
    text = "Summary of the discussion went well.\nThe analysis was long."
    assert not required_sections(text, {"sections": ["Summary"]}).passed
    assert not required_sections(text, {"sections": ["Analysis"]}).passed


def test_required_sections_case_sensitivity():
    assert passed(required_sections("# summary\nx", {"sections": ["Summary"]}))
    strict = {"sections": ["Summary"], "case_sensitive": True}
    assert not required_sections("# summary\nx", strict).passed
    assert passed(required_sections("# Summary\nx", strict))


def test_required_sections_normalizes_whitespace_in_names():
    assert passed(required_sections("##   Key    Findings  \nx", {"sections": ["Key Findings"]}))
    assert passed(required_sections("# Key Findings\nx", {"sections": ["  Key   Findings "]}))


def test_required_sections_ignores_very_long_lines_and_empty_responses():
    assert not required_sections("# " + "Summary " * 100, {"sections": ["Summary"]}).passed
    assert not required_sections("", {"sections": ["Summary"]}).passed


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"sections": []},
        {"sections": "Summary"},
        {"sections": [""]},
        {"sections": ["  "]},
        {"sections": [1]},
        {"sections": ["x" * 101]},
        {"sections": ["a"] * 21},
        {"sections": ["a"], "case_sensitive": "no"},
    ],
)
def test_invalid_section_parameters_raise(parameters):
    with pytest.raises(ParameterError):
        required_sections("# a", parameters)


# ---------------------------------------------------------------------------------------------
# Cross-cutting robustness
# ---------------------------------------------------------------------------------------------

VALID_PARAMETERS = {
    "regex_match": {"pattern": r"\d"},
    "regex_not_match": {"pattern": r"\d"},
    "email_format": {},
    "url_format": {},
    "numeric_exact": {"expected": 1},
    "numeric_range": {"minimum": 0, "maximum": 5},
    "numeric_tolerance": {"expected": 1, "tolerance": 1},
    "word_count_min": {"minimum": 1},
    "word_count_max": {"maximum": 100},
    "required_sections": {"sections": ["A"]},
}

AWKWARD_RESPONSES = [
    "",
    " ",
    "\n\n\n",
    "\x00\x01\x02",
    "\ud83d\ude00 emoji \u202e rtl",
    "x" * 5000,
    "9" * 5000,
    "a@" * 2000,
    "http://" * 500,
    "# " * 1000,
    "1," * 3000,
]


@pytest.mark.parametrize("criterion_id", sorted(EXPECTED_IDS))
def test_no_evaluator_raises_on_awkward_responses(criterion_id):
    evaluator = EVALUATORS[criterion_id]
    for response in AWKWARD_RESPONSES:
        result = evaluator(response, VALID_PARAMETERS[criterion_id])
        assert isinstance(result, EvaluatorResult)
        assert isinstance(result.passed, bool)
        assert result.score in (0.0, 1.0)
        assert 0 < len(result.detail) < 600


@pytest.mark.parametrize("criterion_id", sorted(EXPECTED_IDS))
def test_oversized_responses_fail_cleanly_without_evaluation(criterion_id):
    huge = "word " * (patterns.MAX_RESPONSE_CHARS // 5 + 10)
    result = EVALUATORS[criterion_id](huge, VALID_PARAMETERS[criterion_id])
    assert not result.passed
    assert "at most 100,000" in result.detail


@pytest.mark.parametrize("criterion_id", sorted(EXPECTED_IDS))
def test_non_text_responses_and_non_mapping_parameters_are_rejected(criterion_id):
    evaluator = EVALUATORS[criterion_id]
    with pytest.raises(ParameterError, match="response must be text"):
        evaluator(None, VALID_PARAMETERS[criterion_id])
    with pytest.raises(ParameterError, match="parameters must be an object"):
        evaluator("text", ["not", "a", "mapping"])


def test_evaluators_do_not_mutate_their_inputs():
    parameters = {"sections": ["Summary"], "case_sensitive": False}
    snapshot = {"sections": list(parameters["sections"]), "case_sensitive": False}
    required_sections("# Summary", parameters)
    assert parameters == snapshot


def test_results_are_deterministic():
    first = numeric_tolerance("approx 100.4", {"expected": 100, "tolerance": 1})
    second = numeric_tolerance("approx 100.4", {"expected": 100, "tolerance": 1})
    assert first == second
