import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import {
  assistantMode,
  balanceWeights,
  type ApprovedCriterion,
  type CriterionSuggestion,
} from "./api";

export type Decision = "pending" | "accepted" | "rejected";
export type AssistantStatus = "idle" | "loading" | "loaded" | "error";

export interface SuggestionDraft {
  key: string;
  criterion_id: string;
  reason: string;
  parameters: Record<string, unknown>;
  weight: number;
  decision: Decision;
}

export function toDrafts(suggestions: CriterionSuggestion[], generation: number): SuggestionDraft[] {
  return suggestions.map((suggestion, index) => ({
    key: `${generation}-${index}-${suggestion.criterion_id}`,
    criterion_id: suggestion.criterion_id,
    reason: suggestion.reason,
    parameters: suggestion.parameters,
    weight: suggestion.weight,
    decision: "pending",
  }));
}

function words(name: string): string {
  return name.replace(/_/g, " ");
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/** Reasons one criterion cannot be run as currently edited. */
export function draftProblems(draft: SuggestionDraft): string[] {
  const problems: string[] = [];
  if (!Number.isFinite(draft.weight) || draft.weight < 0 || draft.weight > 100) {
    problems.push("Weight must be a number between 0 and 100.");
  }
  for (const [name, value] of Object.entries(draft.parameters)) {
    if (typeof value === "number" && !Number.isFinite(value)) {
      problems.push(`"${words(name)}" must be a number.`);
    } else if (typeof value === "string" && value.trim() === "") {
      problems.push(`"${words(name)}" must not be empty.`);
    } else if (Array.isArray(value) && value.length === 0) {
      problems.push(`"${words(name)}" needs at least one value.`);
    }
  }
  return problems;
}

export function acceptedDrafts(drafts: SuggestionDraft[]): SuggestionDraft[] {
  return drafts.filter((draft) => draft.decision === "accepted");
}

export function acceptedTotal(drafts: SuggestionDraft[]): number {
  return acceptedDrafts(drafts).reduce(
    (total, draft) => total + (Number.isFinite(draft.weight) ? draft.weight : 0),
    0,
  );
}

/** Everything blocking a run with the accepted criteria; empty when none are accepted. */
export function criteriaIssues(drafts: SuggestionDraft[]): string[] {
  const accepted = acceptedDrafts(drafts);
  if (accepted.length === 0) return [];
  const issues = accepted.flatMap((draft) =>
    draftProblems(draft).map((problem) => `${words(draft.criterion_id)}: ${problem}`),
  );
  const total = acceptedTotal(drafts);
  if (Math.abs(total - 100) > 1e-8) {
    issues.push(`Accepted weights total ${Number(total.toFixed(2))}; they must total 100.`);
  }
  return issues;
}

export function approvedCriteria(drafts: SuggestionDraft[]): ApprovedCriterion[] {
  return acceptedDrafts(drafts).map((draft) => ({
    id: draft.criterion_id,
    parameters: draft.parameters,
    weight: draft.weight,
  }));
}

const cardStyle: CSSProperties = { marginTop: 0, display: "grid", gap: 10 };
const rowStyle: CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10,
};
const actionsStyle: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" };
const listStyle: CSSProperties = { listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 };
const codeStyle: CSSProperties = { fontSize: 11, color: "var(--muted)", marginLeft: 8 };
const pendingBadgeStyle: CSSProperties = { background: "#eceee6", color: "var(--muted)" };
const activeButtonStyle: CSSProperties = { background: "var(--lime)", borderColor: "var(--green)" };
const flatParagraph: CSSProperties = { margin: 0 };

/** Text input that keeps its own raw text so partially typed values are not overwritten. */
function NumberField({
  caption,
  value,
  onChange,
}: {
  caption: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const [text, setText] = useState(Number.isFinite(value) ? String(value) : "");

  // Re-sync when the value changes from outside (for example "Balance weights to 100"), but
  // never overwrite text the user is still typing that already parses to the same number.
  useEffect(() => {
    const parsed = text.trim() === "" ? Number.NaN : Number(text);
    const same = Object.is(parsed, value) || (Number.isNaN(parsed) && Number.isNaN(value));
    if (!same) setText(Number.isFinite(value) ? String(value) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <label className="field">
      <span>{caption}</span>
      <input
        inputMode="decimal"
        value={text}
        onChange={(event) => {
          const raw = event.target.value;
          setText(raw);
          onChange(raw.trim() === "" ? Number.NaN : Number(raw));
        }}
      />
    </label>
  );
}

function ListField({
  caption,
  value,
  onChange,
}: {
  caption: string;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const [text, setText] = useState(value.join(", "));
  return (
    <label className="field">
      <span>{caption} (comma separated)</span>
      <input
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          onChange(
            event.target.value
              .split(",")
              .map((item) => item.trim())
              .filter((item) => item.length > 0),
          );
        }}
      />
    </label>
  );
}

function ParameterField({
  name,
  value,
  onChange,
}: {
  name: string;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const caption = words(name);
  if (typeof value === "string") {
    return (
      <label className="field">
        <span>{caption}</span>
        <input value={value} onChange={(event) => onChange(event.target.value)} />
      </label>
    );
  }
  if (typeof value === "number") {
    return <NumberField caption={caption} value={value} onChange={onChange} />;
  }
  if (typeof value === "boolean") {
    return (
      <label style={{ ...actionsStyle, fontSize: 13, fontWeight: 750 }}>
        <input
          type="checkbox"
          checked={value}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{caption}</span>
      </label>
    );
  }
  if (isStringArray(value)) {
    return <ListField caption={caption} value={value} onChange={onChange} />;
  }
  return (
    <div className="field">
      <span>{caption} (read only)</span>
      <code style={{ fontSize: 12, overflowWrap: "anywhere" }}>{JSON.stringify(value)}</code>
    </div>
  );
}

function CriteriaSuggestions({
  status,
  error,
  drafts,
  ignored,
  onChange,
}: {
  status: AssistantStatus;
  error: string;
  drafts: SuggestionDraft[];
  ignored: number;
  onChange: (drafts: SuggestionDraft[]) => void;
}) {
  const accepted = acceptedDrafts(drafts);
  const pending = drafts.filter((draft) => draft.decision === "pending").length;
  const issues = criteriaIssues(drafts);
  const total = acceptedTotal(drafts);

  function patch(key: string, changes: Partial<SuggestionDraft>) {
    onChange(drafts.map((draft) => (draft.key === key ? { ...draft, ...changes } : draft)));
  }

  function decide(draft: SuggestionDraft, decision: Decision) {
    patch(draft.key, { decision: draft.decision === decision ? "pending" : decision });
  }

  function setParameter(draft: SuggestionDraft, name: string, value: unknown) {
    patch(draft.key, { parameters: { ...draft.parameters, [name]: value } });
  }

  function balance() {
    const balanced = balanceWeights(accepted.map((draft) => draft.weight));
    const byKey = new Map(accepted.map((draft, index) => [draft.key, balanced[index]]));
    onChange(
      drafts.map((draft) => (byKey.has(draft.key) ? { ...draft, weight: byKey.get(draft.key)! } : draft)),
    );
  }

  return (
    <div style={{ display: "grid", gap: 10 }} aria-live="polite">
      {assistantMode === "mock" && (
        <p className="muted test-version-note" style={flatParagraph}>
          Sample suggestions: the criteria assistant is not connected yet.
        </p>
      )}

      {status === "loading" && (
        <p className="muted" role="status" style={flatParagraph}>
          Generating criteria&hellip;
        </p>
      )}

      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}

      {status === "loaded" && drafts.length === 0 && (
        <p className="muted" role="status" style={flatParagraph}>
          {ignored > 0
            ? `None of the assistant's ${ignored} suggestion(s) could be used because they were malformed. Try rewording the objective.`
            : "The assistant did not suggest any criteria for this objective. Describe what a good response must include and try again."}
        </p>
      )}

      {drafts.length > 0 && status !== "loading" && (
        <>
          {ignored > 0 && (
            <p className="muted test-version-note" style={flatParagraph}>
              {ignored} malformed suggestion(s) were ignored.
            </p>
          )}

          <div style={rowStyle}>
            <div style={actionsStyle}>
              <button
                type="button"
                className="new-test-button"
                onClick={() =>
                  onChange(drafts.map((draft) => ({ ...draft, decision: "accepted" as Decision })))
                }
              >
                Accept all
              </button>
              <button
                type="button"
                className="new-test-button"
                onClick={balance}
                disabled={accepted.length === 0}
              >
                Balance weights to 100
              </button>
            </div>
            <output
              className={`score-total ${accepted.length === 0 || issues.length === 0 ? "" : "bad"}`}
              aria-label="Accepted weight total"
            >
              {Number(total.toFixed(2))} / 100
            </output>
          </div>

          <ul style={listStyle}>
            {drafts.map((draft) => {
              const problems = draftProblems(draft);
              const rejected = draft.decision === "rejected";
              return (
                <li key={draft.key} className="scoring-box" style={cardStyle}>
                  <div style={rowStyle}>
                    <div>
                      <strong>{words(draft.criterion_id)}</strong>
                      <code style={codeStyle}>{draft.criterion_id}</code>
                    </div>
                    <span
                      className={`badge ${rejected ? "fail" : ""}`}
                      style={draft.decision === "pending" ? pendingBadgeStyle : undefined}
                    >
                      {draft.decision.toUpperCase()}
                    </span>
                  </div>

                  <p className="muted" style={flatParagraph}>
                    {draft.reason || "No explanation provided."}
                  </p>

                  {!rejected && (
                    <div className="field-row">
                      {Object.entries(draft.parameters).map(([name, value]) => (
                        <ParameterField
                          key={`${draft.key}-${name}`}
                          name={name}
                          value={value}
                          onChange={(next) => setParameter(draft, name, next)}
                        />
                      ))}
                      <NumberField
                        key={`${draft.key}-weight`}
                        caption="Weight"
                        value={draft.weight}
                        onChange={(weight) => patch(draft.key, { weight })}
                      />
                    </div>
                  )}

                  {draft.decision === "accepted" && problems.length > 0 && (
                    <p className="error-text" role="alert">
                      {problems.join(" ")}
                    </p>
                  )}

                  <div style={actionsStyle}>
                    <button
                      type="button"
                      className="new-test-button"
                      aria-pressed={draft.decision === "accepted"}
                      aria-label={`Accept ${words(draft.criterion_id)}`}
                      style={draft.decision === "accepted" ? activeButtonStyle : undefined}
                      onClick={() => decide(draft, "accepted")}
                    >
                      {draft.decision === "accepted" ? "Accepted" : "Accept"}
                    </button>
                    <button
                      type="button"
                      className="new-test-button"
                      aria-pressed={rejected}
                      aria-label={`Reject ${words(draft.criterion_id)}`}
                      style={rejected ? activeButtonStyle : undefined}
                      onClick={() => decide(draft, "rejected")}
                    >
                      {rejected ? "Rejected" : "Reject"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>

          <p className="score-note" style={flatParagraph}>
            {accepted.length === 0
              ? "Accept at least one criterion to score this run with the assistant's suggestions. With none accepted, the standard six-criterion scoring is used."
              : `${accepted.length} accepted${pending > 0 ? `, ${pending} undecided (not used)` : ""}. Accepted weights must total 100.`}
          </p>
          {accepted.length > 0 && Math.abs(total - 100) > 1e-8 && (
            <p className="error-text" role="alert">
              Accepted weights total {Number(total.toFixed(2))}; they must total 100.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default CriteriaSuggestions;
