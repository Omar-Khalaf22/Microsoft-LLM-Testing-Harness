import { useState } from "react";
import { customRubricMethod } from "./api";
import type { CriterionConfiguration, CriterionDefinition, CustomRules } from "./api";
import CriterionPicker from "./CriterionPicker";
export interface CriterionDraft {
  criterion_id: string;
  method?: string;
  custom?: CustomRules;
  parametersText: string;
  weightText: string;
  included: boolean;
  reason?: string;
}
type RowProblems = Partial<Record<"parameters" | "weight" | "title" | "rules" | "reference", string>>;

export function criterionDraft(config: CriterionConfiguration): CriterionDraft {
  const p = config.parameters;
  return {
    criterion_id: config.criterion_id,
    method: config.method,
    custom: config.method ? {
      title: String(p.title ?? ""),
      instructions: String(p.instructions ?? ""),
      reference_evidence: String(p.reference_evidence ?? ""),
      requires_reference: p.requires_reference === true,
    } : undefined,
    parametersText: JSON.stringify(p, null, 2),
    weightText: String(config.weight),
    included: true,
  };
}

export function rowProblems(row: CriterionDraft): RowProblems {
  const problems: RowProblems = {};
  if (row.custom) {
    if (!row.custom.title.trim()) problems.title = "Enter a criterion title.";
    if (!row.custom.instructions.trim()) problems.rules = "Enter scoring instructions.";
    if (row.custom.requires_reference && !row.custom.reference_evidence.trim())
      problems.reference = "Enter reference evidence for factual verification.";
  } else {
    try {
      const value: unknown = JSON.parse(row.parametersText);
      if (value === null || typeof value !== "object" || Array.isArray(value))
        problems.parameters = 'Enter a JSON object such as {"keywords": ["alpha"]}.';
    } catch {
      problems.parameters = "Check the parameter JSON syntax.";
    }
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
  const available = catalog.filter((c) => !rows.some((r) => r.criterion_id === c.id));
  const selected = available.find((c) => c.id === addId);
  function change(index: number, patch: Partial<CriterionDraft>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }
  function nextWeight() {
    const remaining =
      100 -
      rows
        .filter((r) => r.included)
        .reduce((s, r) => s + Number(r.weightText || 0), 0);
    return String(remaining > 0 ? Number(remaining.toFixed(2)) : 1);
  }
  function add() {
    if (!selected) return;
    onChange([
      ...rows,
      {
        criterion_id: selected.id,
        parametersText: JSON.stringify(selected.example_parameters, null, 2),
        weightText: nextWeight(),
        included: true,
      },
    ]);
    setAddId("");
  }
  function addCustom() {
    onChange([...rows, {
      criterion_id: `custom_${crypto.randomUUID().replaceAll("-", "")}`,
      method: customRubricMethod,
      custom: { title: "", instructions: "", reference_evidence: "", requires_reference: false },
      parametersText: "",
      weightText: nextWeight(),
      included: true,
    }]);
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
        const title = row.custom ? row.custom.title.trim() || "Custom criterion" : def?.name ?? row.criterion_id;
        const parametersError = `parameters-error-${row.criterion_id}`;
        const weightError = `points-error-${row.criterion_id}`;
        return (
          <fieldset
            className="criterion-editor"
            key={row.criterion_id}
            disabled={disabled}
          >
            <legend>{title}</legend>
            <label className="check-field">
              <input
                type="checkbox"
                checked={row.included}
                onChange={(e) => change(index, { included: e.target.checked })}
              />
              Include {title}
            </label>
            <p>{def?.description}</p>
            {row.reason && (
              <p className="suggestion-reason">{row.reason}</p>
            )}
            {row.custom && (
              <CustomFields
                row={row.custom}
                id={row.criterion_id}
                problems={problems}
                onChange={(patch) => change(index, { custom: { ...row.custom!, ...patch } })}
              />
            )}
            <div className="criterion-edit-fields">
              {!row.custom && <label className="field">
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
              </label>}
              <label className="field">
                <span>Maximum points for {title}</span>
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
            {!row.custom && <details>
              <summary>Parameter format</summary>
              <pre className="parameter-schema">
                {JSON.stringify(def?.parameter_schema ?? {}, null, 2)}
              </pre>
            </details>}
            <button
              type="button"
              className="text-button"
              onClick={() => onChange(rows.filter((_, i) => i !== index))}
            >
              Remove {title}
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
        <CriterionPicker
          options={available}
          selectedId={selected?.id ?? ""}
          onSelect={setAddId}
          disabled={disabled}
        />
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || !selected}
          onClick={add}
        >
          Add criterion
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || rows.length >= 100}
          onClick={addCustom}
        >
          Add custom criterion
        </button>
      </div>
    </section>
  );
}

function CustomFields({
  row, id, problems, onChange,
}: {
  row: CustomRules;
  id: string;
  problems: RowProblems;
  onChange: (patch: Partial<CustomRules>) => void;
}) {
  const describedBy = (field: keyof RowProblems, hint?: string) =>
    [hint && `${id}-${hint}`, problems[field] && `${id}-${field}-error`].filter(Boolean).join(" ") || undefined;
  const error = (field: keyof RowProblems) => problems[field] && (
    <span className="error-text" id={`${id}-${field}-error`} role="alert">{problems[field]}</span>
  );
  return (
    <div className="custom-criterion-fields">
      <div className="field">
        <label htmlFor={`${id}-title`}>Criterion title</label>
        <input id={`${id}-title`} maxLength={100} value={row.title}
          aria-invalid={!!problems.title} aria-describedby={describedBy("title")}
          onChange={(e) => onChange({ title: e.target.value })} />
        {error("title")}
      </div>
      <div className="field">
        <label htmlFor={`${id}-rules`}>Scoring instructions</label>
        <textarea id={`${id}-rules`} rows={4} maxLength={6000} value={row.instructions}
          aria-invalid={!!problems.rules} aria-describedby={describedBy("rules", "rules-hint")}
          onChange={(e) => onChange({ instructions: e.target.value })} />
        <small className="muted" id={`${id}-rules-hint`}>
          Describe what earns full, partial, and zero credit. Include edge cases in these rules.
        </small>
        {error("rules")}
      </div>
      <label className="check-field">
        <input type="checkbox" checked={row.requires_reference}
          onChange={(e) => onChange({ requires_reference: e.target.checked })} />
        Verifies factual claims
      </label>
      <div className="field">
        <label htmlFor={`${id}-reference`}>Judge-only reference evidence or example answer</label>
        <textarea id={`${id}-reference`} rows={3} maxLength={10000} value={row.reference_evidence}
          aria-invalid={!!problems.reference} aria-describedby={describedBy("reference", "reference-hint")}
          onChange={(e) => onChange({ reference_evidence: e.target.value })} />
        <small className="muted" id={`${id}-reference-hint`}>
          Only the judge receives this text. Supply a reference when verifying factual claims.
        </small>
        {error("reference")}
      </div>
    </div>
  );
}
