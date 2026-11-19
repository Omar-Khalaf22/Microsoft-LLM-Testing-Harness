"""Deterministic scoring from recorded model execution metadata."""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    """Evaluate a recorded metric; never infer missing telemetry from response text."""
    if not isinstance(context, dict):
        raise ValueError("Execution context must be an object")
    metrics = context.get("recorded_execution_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Recorded execution metrics are required")
    metric_key = {
        "latency_budget": "latency_ms",
        "response_time": "latency_ms",
        "token_budget": "total_tokens",
    }[criterion_id]
    measured = metrics.get(metric_key)
    if isinstance(measured, bool) or not isinstance(measured, (int, float)):
        raise ValueError(f"Recorded {metric_key} must be numeric")
    if not 0 <= measured < float("inf"):
        raise ValueError(f"Recorded {metric_key} must be finite and nonnegative")
    budget = parameters["maximum"]
    passed = measured <= budget
    score = 1.0 if measured == 0 else min(1.0, budget / measured)
    return passed, score, f"Recorded {metric_key}: {measured}; budget: {budget}"
