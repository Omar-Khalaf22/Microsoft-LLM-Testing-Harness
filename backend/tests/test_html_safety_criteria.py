"""Regression tests for conservative HTML policy scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    "html",
    [
        "<p>Safe <strong>text</strong></p>",
        '<a href="https://example.org">Reference</a>',
        "<div>Plain content</div>",
    ],
)
def test_safe_html(html):
    assert evaluate_criterion("html_safety", html, {}, {})[:2] == (True, 1.0)


@pytest.mark.parametrize(
    "html",
    [
        "<script>alert(1)</script>",
        '<img src="javascript:alert(1)">',
        '<a href="java&#x73;cript:alert(1)">link</a>',
        '<div onclick="evil()">click</div>',
        '<iframe src="https://example.org"></iframe>',
        '<div style="color:red">text</div>',
        '<a href="data:text/html,evil">link</a>',
        '<a href="//example.org">link</a>',
        '<svg onload="evil()"></svg>',
    ],
)
def test_unsafe_html(html):
    passed, score, detail = evaluate_criterion("html_safety", html, {}, {})
    assert not passed
    assert score == 0.0
    assert detail


def test_reject_unknown_parameters():
    with pytest.raises(ValueError):
        validate_criterion("html_safety", {"ignore_scripts": True})
