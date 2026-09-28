// Implements SRS Requirement 1 (Configurable Scoring): the user selects which
// evaluation criteria apply to a test and assigns each a custom point value
// that must sum to 100 (Spec 1.1, Spec 1.2).
//
// The six criteria here mirror the ones the backend's scoring engine already
// computes (backend/app/evaluation/scoring.py), with its fixed default point
// split (30/20/15/15/10/10). NOTE: the live POST /runs schema on every branch
// declares `extra="forbid"`, so a custom-weights field would be rejected by
// the real backend today. This component is fully functional client-side
// (selection, point values, and the sum-to-100 validation the SRS requires)
// but its output is not yet submitted with the run request — see the comment
// in RunForm.tsx. Wiring it in only needs a backend schema field to carry it.

export interface ScoringCriterion {
  key: "keyword" | "relevance" | "length" | "sentences" | "forbidden" | "valid";
  label: string;
  description: string;
  enabled: boolean;
  points: number;
}

export const DEFAULT_SCORING_CRITERIA: ScoringCriterion[] = [
  {
    key: "keyword",
    label: "Keyword coverage",
    description: "Response contains the expected keywords",
    enabled: true,
    points: 30,
  },
  {
    key: "relevance",
    label: "Prompt relevance",
    description: "Response addresses the meaningful terms in the prompt",
    enabled: true,
    points: 20,
  },
  {
    key: "length",
    label: "Minimum length",
    description: "Response meets the minimum character length",
    enabled: true,
    points: 15,
  },
  {
    key: "sentences",
    label: "Sentence structure",
    description: "Response meets the minimum sentence count",
    enabled: true,
    points: 15,
  },
  {
    key: "forbidden",
    label: "Forbidden terms",
    description: "Response avoids the configured forbidden terms",
    enabled: true,
    points: 10,
  },
  {
    key: "valid",
    label: "Valid response",
    description: "Response is non-empty and usable",
    enabled: true,
    points: 10,
  },
];

export function scoringTotal(criteria: ScoringCriterion[]): number {
  return criteria.filter((c) => c.enabled).reduce((sum, c) => sum + c.points, 0);
}

function ScoringConfig({
  criteria,
  onChange,
}: {
  criteria: ScoringCriterion[];
  onChange: (criteria: ScoringCriterion[]) => void;
}) {
  const total = scoringTotal(criteria);
  const valid = total === 100;

  function updateCriterion(key: ScoringCriterion["key"], patch: Partial<ScoringCriterion>) {
    onChange(criteria.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  }

  return (
    <section className="scoring-box" aria-labelledby="scoring-title">
      <div className="scoring-head">
        <div>
          <h3 id="scoring-title">Scoring configuration</h3>
          <p>Choose which criteria apply and how the 100 points are divided.</p>
        </div>
        <div className={`score-total ${valid ? "" : "bad"}`}>{total} / 100</div>
      </div>

      <div className="score-grid">
        {criteria.map((criterion) => (
          <div className="score-item" key={criterion.key}>
            <label className="score-item-label">
              <input
                type="checkbox"
                checked={criterion.enabled}
                onChange={(event) => updateCriterion(criterion.key, { enabled: event.target.checked })}
              />
              <span>{criterion.label}</span>
            </label>
            <p className="score-item-description">{criterion.description}</p>
            <input
              type="number"
              className="weight-input"
              min={0}
              max={100}
              value={criterion.points}
              disabled={!criterion.enabled}
              onChange={(event) =>
                updateCriterion(criterion.key, { points: Number(event.target.value) })
              }
            />
          </div>
        ))}
      </div>

      <p className="score-note">
        {valid
          ? "Points total 100. This configuration is ready for automated evaluation."
          : "Enabled criteria must total exactly 100 points before running a test."}
      </p>
    </section>
  );
}

export default ScoringConfig;
