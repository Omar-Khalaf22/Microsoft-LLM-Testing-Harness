import { useEffect, useId, useRef, useState } from "react";
import {
  getExecution, listProfiles, requestPreview, reserveExecution, rerunVersion, testReference,
} from "./api";
import type {
  Attempt, Execution, ExecutionSelection, ModelProfile, Preview, SavedTestVersion,
} from "./api";

export function useReservation(onReserved: (execution: Execution) => void) {
  const request = useRef<{ fingerprint: string; key: string } | null>(null);
  const active = useRef(false);
  const [reserving, setReserving] = useState(false);
  const [error, setError] = useState("");
  async function reserve(fingerprint: string, submit: (key: string) => Promise<Execution>) {
    if (active.current) return;
    active.current = true;
    setReserving(true);
    setError("");
    if (request.current?.fingerprint !== fingerprint)
      request.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const plan = await submit(request.current.key);
      request.current = null;
      onReserved(plan);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The execution could not be reserved.");
    } finally {
      active.current = false;
      setReserving(false);
    }
  }
  const start = (selection: ExecutionSelection) =>
    reserve(JSON.stringify(selection), (key) => reserveExecution(selection, key));
  return { reserving, error, reserve, start };
}

export function ProfilePicker({
  value, onChange, disabled, label = "Approved target profile",
}: {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  label?: string;
}) {
  const [profiles, setProfiles] = useState<ModelProfile[] | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const profileField = useId();
  useEffect(() => {
    const controller = new AbortController();
    listProfiles(controller.signal)
      .then(setProfiles)
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [retry]);
  return (
    <>
      <div className="field">
        <label htmlFor={profileField}>{label}</label>
        <select id={profileField} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled || !profiles?.length}>
          <option value="">{profiles ? "Choose a profile" : "Loading profiles…"}</option>
          {profiles?.map((p) => <option key={p.profile_id} value={p.profile_id}>
            {p.profile_id} · {p.requested_model} · revision {p.profile_revision}
            {p.parameters.temperature !== undefined ? ` · temperature ${p.parameters.temperature}` : ""}
          </option>)}
        </select>
      </div>
      {profiles?.length === 0 && <p className="muted">No approved target profiles are configured.</p>}
      {error && <p role="alert" className="error-text">
        {error} <button type="button" onClick={() => { setError(""); setRetry(retry + 1); }}>Reload profiles</button>
      </p>}
    </>
  );
}

const previewFields = [
  ["purpose", "Purpose"], ["deliverable", "Deliverable"],
  ["constraints", "Constraints"], ["success_conditions", "Success conditions"],
];
const previewErrors = {
  timeout: "The target timed out.",
  provider_unavailable: "The target provider could not return a preview.",
  invalid_response: "The target did not return all four interpretation fields.",
};

export default function SavedExecution({
  test, onReserved,
}: {
  test: SavedTestVersion;
  onReserved: (execution: Execution) => void;
}) {
  const [profile, setProfile] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const previewRequest = useRef<AbortController | null>(null);
  const { start, error, reserving } = useReservation(onReserved);
  const busy = reserving || previewing;
  useEffect(() => () => previewRequest.current?.abort(), []);

  async function interpret() {
    if (previewRequest.current) return;
    const controller = new AbortController();
    previewRequest.current = controller;
    setPreviewing(true);
    setPreview(null);
    setReviewed(false);
    setPreviewError("");
    try {
      setPreview(await requestPreview(test, profile, controller.signal));
    } catch (e) {
      if (!controller.signal.aborted)
        setPreviewError(e instanceof Error ? e.message : "The preview could not be loaded.");
    } finally {
      previewRequest.current = null;
      if (!controller.signal.aborted) setPreviewing(false);
    }
  }
  const startRun = () => start({
    test: testReference(test),
    profile_ids: [profile],
    ...(preview ? {
      previews: {
        "1:1": {
          preview_id: preview.preview_id,
          confirmed: preview.status === "completed",
          acknowledge_error: preview.status === "technical_error",
        },
      },
    } : {}),
  });
  return (
    <section className="saved-execution" aria-label="Execute approved test">
      <h3>Execute version {test.test_version}</h3>
      <ProfilePicker value={profile} disabled={busy} onChange={(value) => {
        setProfile(value);
        setPreview(null);
        setPreviewError("");
        setReviewed(false);
      }} />
      <button type="button" className="secondary-button" onClick={() => void interpret()} disabled={!profile || busy}>
        {previewing ? "Requesting preview…" : preview || previewError ? "Retry preview" : "Request interpretation preview"}
      </button>
      {previewError && <p role="alert" className="error-text">{previewError}</p>}
      {preview && <div className="preview-card">
        <div className="response-box">
          <h4>Original task</h4>
          <p>{test.definition.prompt}</p>
          <details>
            <summary>Effective system instructions</summary>
            <p>{test.definition.resolved_system_prompt}</p>
          </details>
        </div>
        {preview.status === "completed" ? (
          <>
            <h4>Interpretation from {preview.actual_model}</h4>
            <dl className="execution-metrics-grid">
              {previewFields.map(([key, label]) => (
                <div key={key}><dt>{label}</dt><dd>{preview.interpretation[key]}</dd></div>
              ))}
            </dl>
          </>
        ) : (
          <p role="alert" className="error-text">
            {preview.error_category ? previewErrors[preview.error_category] : "The preview could not complete."}
          </p>
        )}
        <label className="check-field">
          <input type="checkbox" checked={reviewed} disabled={busy}
            onChange={(e) => setReviewed(e.target.checked)} />
          {preview.status === "completed"
            ? "I reviewed this interpretation"
            : "I acknowledge the preview error and want to continue"}
        </label>
      </div>}
      {error && <p role="alert" className="error-text">{error}</p>}
      <button type="button" className="primary-button" onClick={() => void startRun()}
        disabled={!profile || busy || !!previewError || (!!preview && !reviewed)}>
        {reserving ? "Reserving run…" : "Run approved version"}
      </button>
    </section>
  );
}

export function RerunButton({ runId, onReserved }: {
  runId: string; onReserved: (execution: Execution) => void;
}) {
  const { reserve, reserving, error } = useReservation(onReserved);
  return (
    <>
      <button type="button" className="secondary-button" disabled={reserving}
        onClick={() => void reserve(runId, (key) => rerunVersion(runId, key))}>
        {reserving ? "Reserving rerun…" : "Rerun approved version"}
      </button>
      {error && <p role="alert" className="error-text">{error}</p>}
    </>
  );
}

export function ExecutionProgress({ initial, onFinished, onOpen }: {
  initial: Execution;
  onFinished: (execution: Execution) => void;
  onOpen: (attempt: Attempt) => void;
}) {
  const [plan, setPlan] = useState(initial);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: number;
    async function poll(current: Execution) {
      if (controller.signal.aborted) return;
      if (current.status === "completed" || current.status === "failed") {
        setPlan(current);
        onFinished(current);
        return;
      }
      try {
        const next = await getExecution(current.execution_id, controller.signal);
        if (controller.signal.aborted) return;
        setPlan(next);
        setError("");
        if (next.status === "completed" || next.status === "failed") {
          onFinished(next);
          return;
        }
        timer = window.setTimeout(() => void poll(next), 750);
      } catch (e) {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Progress is temporarily unavailable.");
        timer = window.setTimeout(() => void poll(current), 2000);
      }
    }
    void poll(initial);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [initial, onFinished]);
  const { pending, running, completed, failed } = plan.progress;
  return (
    <section className="panel execution-progress" aria-label="Execution progress"
      data-execution-id={plan.execution_id}>
      <h2>Execution progress</h2>
      <p role="status">{completed} completed · {failed} failed · {running} running · {pending} pending</p>
      {error && <p role="alert" className="error-text">{error}</p>}
      <ol className="attempt-list">
        {plan.attempts.map((attempt) => <li key={attempt.run_id}>
          <span>Item {attempt.suite_position} · model {attempt.model_position} · version {attempt.test_version} · {attempt.status}</span>
          {(attempt.status === "completed" || attempt.status === "failed") &&
            <button type="button" className="text-button" onClick={() => onOpen(attempt)}>
              View item {attempt.suite_position} model {attempt.model_position} result
            </button>}
        </li>)}
      </ol>
    </section>
  );
}
