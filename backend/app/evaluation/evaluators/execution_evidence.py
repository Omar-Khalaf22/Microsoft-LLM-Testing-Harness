"""Score results supplied by an external isolated code execution service.

This evaluator never executes untrusted model output in the API process.
Execution evidence must come from a trusted isolated runtime integration.
"""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id not in {"code_execution", "unit_test_pass"}:
        raise ValueError("Unknown code execution criterion")
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Nonempty generated code is required")
    if not isinstance(context, dict):
        raise ValueError("Execution context must be an object")
    evidence = context.get("execution_result")
    if not isinstance(evidence, dict):
        raise ValueError("Trusted isolated execution_result is required")
    if evidence.get("runtime") != parameters["isolated_runtime"]:
        raise ValueError("Execution runtime does not match the configured runtime")
    if evidence.get("language") != parameters["language"]:
        raise ValueError("Execution language does not match the configured language")
    if evidence.get("source") != response:
        raise ValueError("Execution evidence does not match the candidate source")
    if evidence.get("trusted") is not True:
        raise ValueError("Only trusted isolated execution evidence is accepted")
    if evidence.get("timed_out") is not False:
        return False, 0.0, "Execution timed out or timeout status is missing"
    if criterion_id == "code_execution":
        exit_code = evidence.get("exit_code")
        if type(exit_code) is not int:
            raise ValueError("Execution exit_code must be an integer")
        passed = exit_code == 0
        return passed, float(passed), f"Isolated runtime exit code: {exit_code}"
    results = evidence.get("test_results")
    if not isinstance(results, list) or len(results) != len(parameters["test_cases"]):
        raise ValueError("One execution result is required for every configured test")
    expected_ids = [case["id"] for case in parameters["test_cases"]]
    ids = [result.get("id") for result in results if isinstance(result, dict)]
    if len(ids) != len(expected_ids) or set(ids) != set(expected_ids):
        raise ValueError("Test result IDs must match configured test case IDs")
    if any(type(result.get("passed")) is not bool for result in results):
        raise ValueError("Every test result must contain a boolean passed value")
    passed_count = sum(result["passed"] for result in results)
    score = passed_count / len(results)
    return (
        passed_count == len(results),
        score,
        f"Isolated runtime tests passed: {passed_count}/{len(results)}",
    )
