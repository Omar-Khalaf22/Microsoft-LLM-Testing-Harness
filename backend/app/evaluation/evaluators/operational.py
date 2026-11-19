"""Strict deterministic checks for tool selection and recorded execution cost."""

from math import isfinite


def _number(value, name):
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return value


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if not isinstance(context, dict):
        raise ValueError("Evaluation context must be an object")
    if criterion_id == "tool_selection":
        expected = context.get("expected_tool_names")
        actual = context.get("actual_tool_names")
        if not isinstance(expected, list) or not isinstance(actual, list):
            raise ValueError("Expected and actual tool name lists are required")
        if any(not isinstance(x, str) or not x.strip() for x in expected + actual):
            raise ValueError("Tool names must be nonempty strings")
        if len(expected) > 100 or len(actual) > 100:
            raise ValueError("Tool call lists exceed the limit")
        from collections import Counter

        wanted, observed = Counter(expected), Counter(actual)
        matched = sum((wanted & observed).values())
        precision = matched / len(actual) if actual else float(not expected)
        recall = matched / len(expected) if expected else float(not actual)
        score = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        passed = score >= parameters["minimum_score"]
        return passed, score, f"Matched calls: {matched}; F1: {score:.4f}"

    if criterion_id == "cost_budget":
        metrics = context.get("recorded_execution_metrics")
        prices = context.get("versioned_price_map")
        if not isinstance(metrics, dict) or not isinstance(prices, dict):
            raise ValueError("Recorded token usage and versioned price map are required")
        model = metrics.get("model")
        if not isinstance(model, str) or not model or model not in prices:
            raise ValueError("Recorded model must match a priced model")
        entry = prices[model]
        if not isinstance(entry, dict) or not isinstance(entry.get("version"), str):
            raise ValueError("A versioned price entry is required")
        if not entry["version"].strip():
            raise ValueError("Price version cannot be empty")
        input_tokens = _number(metrics.get("input_tokens"), "input_tokens")
        output_tokens = _number(metrics.get("output_tokens"), "output_tokens")
        input_price = _number(entry.get("input_per_million"), "input_per_million")
        output_price = _number(entry.get("output_per_million"), "output_per_million")
        cost = (
            input_tokens * input_price + output_tokens * output_price
        ) / 1_000_000
        budget = parameters["maximum_usd"]
        score = 1.0 if cost == 0 else min(1.0, budget / cost)
        return cost <= budget, score, f"Recorded cost USD: {cost:.8f}; budget: {budget}"

    raise ValueError("Unknown deterministic criterion")
