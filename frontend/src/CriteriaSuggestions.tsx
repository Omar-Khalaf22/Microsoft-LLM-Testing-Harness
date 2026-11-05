import { useState } from "react";
import type { CriterionDefinition } from "./api";
export interface CriterionDraft {
  criterion_id: string;
  parametersText: string;
  weightText: string;
  included: boolean;
  reason?: string;
}
function rowProblems(row: CriterionDraft): {
  parameters?: string;
  weight?: string;
} {
  const problems: { parameters?: string; weight?: string } = {};
  try {
    const value: unknown = JSON.parse(row.parametersText);
    if (value === null || typeof value !== "object" || Array.isArray(value))
      problems.parameters =
        'Parameters must be a JSON object, for example {"keywords": ["alpha"]}.';
  } catch (e) {
    problems.parameters = `Not valid JSON: ${e instanceof Error ? e.message : "check the syntax"}`;
  }
  const points = Number(row.weightText);
  if (row.weightText.trim() === "" || !Number.isFinite(points) || points <= 0 || points > 100)
    problems.weight = "Enter points above 0 and up to 100.";
  else if (Math.abs(points * 100 - Math.round(points * 100)) > 1e-8)
    problems.weight = "Use at most two decimal places.";
  return problems;
}
export default function CriteriaSuggestions({
  catalog,
  rows,
  onChange,
  disabled,
}: {
  catalog: CriterionDefinition[];
  rows: CriterionDraft[];
  onChange: (rows: CriterionDraft[]) => void;
  disabled: boolean;
}) {
  const [addId, setAddId] = useState("");
  function change(index: number, patch: Partial<CriterionDraft>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }
  function add() {
    const def = catalog.find((c) => c.id === addId);
    if (!def) return;
    const remaining =
      100 -
      rows
        .filter((r) => r.included)
        .reduce((s, r) => s + Number(r.weightText || 0), 0);
    onChange([
      ...rows,
      {
        criterion_id: def.id,
        parametersText: JSON.stringify(def.example_parameters, null, 2),
        weightText: String(remaining > 0 ? Number(remaining.toFixed(2)) : 1),
        included: true,
      },
    ]);
    setAddId("");
  }
  return (
    <section className="criteria-editor" aria-labelledby="criteria-title">
      <h3 id="criteria-title">Criteria to evaluate</h3>
      <p className="muted">
        Review each condition, edit its parameters, and allocate exactly 100.00
        points.
      </p>
      {rows.length > 0 && (
        <button
          type="button"
          className="secondary-button"
          disabled={disabled}
          onClick={() => onChange(rows.map((r) => ({ ...r, included: true })))}
        >
          Include all listed criteria
        </button>
      )}
      {rows.map((row, index) => {
        const def = catalog.find((c) => c.id === row.criterion_id);
        const problems = row.included ? rowProblems(row) : {};
        const parametersError = `parameters-error-${row.criterion_id}`;
        const weightError = `points-error-${row.criterion_id}`;
        return (
          <fieldset
            className="criterion-editor"
            key={row.criterion_id}
            disabled={disabled}
          >
            <legend>{def?.name ?? row.criterion_id}</legend>
            <label className="check-field">
              <input
                type="checkbox"
                checked={row.included}
                onChange={(e) => change(index, { included: e.target.checked })}
              />
              Include {def?.name ?? row.criterion_id}
            </label>
            <p>{def?.description}</p>
            {row.reason && (
              <p className="suggestion-reason">Why suggested: {row.reason}</p>
            )}
            <div className="criterion-edit-fields">
              <label className="field">
                <span>
                  Parameters for {def?.name ?? row.criterion_id} (JSON)
                </span>
                <textarea
                  className="parameter-input"
                  spellCheck={false}
                  rows={3}
                  value={row.parametersText}
                  aria-invalid={problems.parameters ? true : undefined}
                  aria-describedby={problems.parameters ? parametersError : undefined}
                  onChange={(e) =>
                    change(index, { parametersText: e.target.value })
                  }
                />
                {problems.parameters && (
                  <span id={parametersError} className="error-text" role="alert">
                    {problems.parameters}
                  </span>
                )}
              </label>
              <label className="field">
                <span>Maximum points for {def?.name ?? row.criterion_id}</span>
                <input
                  type="number"
                  min="0.01"
                  max="100"
                  step="0.01"
                  value={row.weightText}
                  aria-invalid={problems.weight ? true : undefined}
                  aria-describedby={problems.weight ? weightError : undefined}
                  onChange={(e) =>
                    change(index, { weightText: e.target.value })
                  }
                />
                {problems.weight && (
                  <span id={weightError} className="error-text" role="alert">
                    {problems.weight}
                  </span>
                )}
              </label>
            </div>
            <details>
              <summary>Parameter format</summary>
              <pre className="parameter-schema">
                {JSON.stringify(def?.parameter_schema ?? {}, null, 2)}
              </pre>
            </details>
            <button
              type="button"
              className="text-button"
              onClick={() => onChange(rows.filter((_, i) => i !== index))}
            >
              Remove {def?.name ?? row.criterion_id}
            </button>
          </fieldset>
        );
      })}
      {rows.length === 0 && (
        <p className="muted">
          Generate suggestions above or add a criterion below.
        </p>
      )}
      <div className="add-criterion">
        <label className="field">
          <span>Add a supported criterion</span>
          <select
            value={addId}
            onChange={(e) => setAddId(e.target.value)}
            disabled={disabled}
          >
            <option value="">Choose a criterion</option>
            {catalog
              .filter((c) => !rows.some((r) => r.criterion_id === c.id))
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.category}
                </option>
              ))}
          </select>
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || !addId}
          onClick={add}
        >
          Add criterion
        </button>
      </div>
    </section>
  );
}
