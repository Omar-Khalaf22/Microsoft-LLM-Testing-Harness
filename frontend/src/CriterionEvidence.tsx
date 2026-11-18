import type { CriterionResult, RunResponse } from "./api";
import { capitalize } from "./titleCase";

export function isJudged(run: RunResponse, criterion: CriterionResult) {
  return !!(
    criterion.evaluator_model ||
    criterion.evidence_excerpts ||
    run.metadata.criteria?.find((c) => c.criterion_id === criterion.criterion_id)?.method ||
    run.metadata.criterion_definitions?.find((c) => c.id === criterion.criterion_id)?.evaluator_type === "rubric"
  );
}

export default function CriterionEvidence({ run, row }: { run: RunResponse; row: CriterionResult }) {
  const judged = isJudged(run, row);
  return (
    <div className="criterion-evidence">
      <p className="muted">
        {judged ? "Model judge" : run.provider === "imported" && !row.criterion_id ? "Archived evaluator" : "Built-in check"}
        {row.evaluator_model && ` · ${row.evaluator_model}`}
        {" · "}{row.status === "error" ? "Incomplete" : capitalize(row.status ?? "Recorded")}
      </p>
      {row.detail && <p>{row.detail}</p>}
      {row.rationale && row.rationale !== row.detail && <p>{row.rationale}</p>}
      {!!row.evidence_excerpts?.length && (
        <ul className="evidence-excerpts" aria-label="Judge evidence excerpts">
          {row.evidence_excerpts.map((entry, i) => (
            <li key={i}><strong>{entry.source === "reference" ? "Scoring reference" : "Target answer"}</strong>{" "}<q>{entry.excerpt}</q></li>
          ))}
        </ul>
      )}
      {!!row.evidence?.length && (
        <ul className="evidence-excerpts" aria-label="Reference excerpts">
          {row.evidence.map((excerpt, i) => <li key={i}><q>{excerpt}</q></li>)}
        </ul>
      )}
    </div>
  );
}
