"""Fictional, deterministic model responses and judge outputs for local verification."""

import json

OUTLOOK_ANSWER = (
    "Alder Rail Systems depends on one supplier for 62% of its battery modules. "
    "The service margin fell from 18% to 12%. "
    "A backup line could support a modest recovery in 2027–2028 if qualification succeeds."
)
OUTLOOK_WEAK_ANSWER = (
    "Alder Rail Systems should grow quickly over the next two years. "
    "One supplier covers 62% of the modules. Growth is certain."
)
MINING_ANSWERS = {
    "demo-mining-a": ["M-205", "M-902", "M-101", "M-318", "M-917"],
    "demo-mining-b": ["M-318", "M-101", "M-832", "M-205", "M-841"],
    "demo-mining-missing": ["M-205", "M-902", "M-101", "M-905", "M-917"],
    "demo-mining-duplicate": ["M-205", "M-101", "M-318", "M-205", "M-917"],
}


def demo_answer(model: str) -> str | None:
    if model in MINING_ANSWERS:
        return json.dumps(MINING_ANSWERS[model])
    return {"demo-outlook-a": OUTLOOK_ANSWER, "demo-outlook-b": OUTLOOK_WEAK_ANSWER}.get(model)


def demo_interpretation(task: str) -> dict[str, str]:
    if "Alder Rail Systems" in task:
        return {
            "purpose": "Assess risks and the outlook for fictional Alder Rail Systems.",
            "deliverable": "A concise 2027–2028 outlook.",
            "constraints": "Use the planning notes and qualify uncertain claims.",
            "success_conditions": "Explain challenges, support claims, and identify uncertainty.",
        }
    if "fictional account IDs" in task:
        return {
            "purpose": "Review the fictional mining opportunities.",
            "deliverable": "A JSON array of five accounts.",
            "constraints": "Use distinct IDs.",
            "success_conditions": "Return five IDs ranked by opportunity.",
        }
    return {
        "purpose": "Interpret the requested task.",
        "deliverable": "An answer to the supplied prompt.",
        "constraints": "Follow the supplied task instructions.",
        "success_conditions": "Address the task and its stated constraints.",
    }


def demo_judgment(payload: dict) -> dict:
    answer, reference = payload["response"], payload["reference_evidence"]
    title = payload.get("rubric", {}).get("title", "") if "method" in payload else ""
    if title == "Material challenges" and answer == OUTLOOK_ANSWER:
        score, rationale = (
            0.75,
            "Both challenges appear. The impact on execution is underdeveloped.",
        )
    elif title == "Support for major claims" and answer == OUTLOOK_ANSWER:
        score, rationale = (
            1,
            "The concentration, margin decline, and conditional recovery follow the packet.",
        )
    elif title == "Two-year outlook with uncertainties" and answer == OUTLOOK_ANSWER:
        score, rationale = (
            0.4,
            "Names a direction and qualification risk. Renewal uncertainty is missing.",
        )
    elif title == "Material challenges" and answer == OUTLOOK_WEAK_ANSWER:
        score, rationale = 0.25, "Names concentration alone without explaining its business impact."
    else:
        score, rationale = (
            0,
            "The local fake has no positive scripted score for this answer and row.",
        )
    evidence = []
    if score:
        reference_excerpt = {
            "Material challenges": "62% of battery modules came from one supplier.",
            "Support for major claims": "Service margin declined from 18% to 12%.",
            "Two-year outlook with uncertainties": "Backup line qualification remains uncertain.",
        }[title]
        answer_excerpt = {
            "Material challenges": "62%",
            "Support for major claims": "The service margin fell from 18% to 12%.",
            "Two-year outlook with uncertainties": "if qualification succeeds",
        }[title]
        if reference_excerpt in reference:
            evidence.append({"source": "reference", "excerpt": reference_excerpt})
        if answer_excerpt in answer:
            evidence.append({"source": "answer", "excerpt": answer_excerpt})
    result = {"score": score, "rationale": rationale, "evidence": evidence}
    if "method" not in payload:
        result["evaluator_model"] = payload["evaluator_model"]
    return result
