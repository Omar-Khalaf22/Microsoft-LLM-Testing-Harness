import { useEffect, useId, useState } from "react";
import { listTests, listVersions } from "./api";
import type { TestReference } from "./api";

type Test = Awaited<ReturnType<typeof listTests>>[number];
type Version = Awaited<ReturnType<typeof listVersions>>[number];

export default function SavedTestPicker({
  approvedOnly = false, disabled = false, onSelect,
}: {
  approvedOnly?: boolean;
  disabled?: boolean;
  onSelect: (version: TestReference & { name: string }) => Promise<void> | void;
}) {
  const [tests, setTests] = useState<Test[]>([]);
  const [testId, setTestId] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [version, setVersion] = useState("");
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const testField = useId();
  const versionField = useId();
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    listTests(controller.signal)
      .then((items) => setTests(items.filter((item) => item.state !== "historical")))
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    if (!testId) return;
    const controller = new AbortController();
    listVersions(testId, controller.signal)
      .then((items) => {
        const choices = items.filter((v) => approvedOnly ? v.state === "approved" : v.state !== "historical");
        setVersions(choices);
        setVersion(choices.length ? String(choices.at(-1)!.test_version) : "");
      })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [testId, approvedOnly, retry]);

  const choice = versions.find((v) => String(v.test_version) === version);
  async function selectVersion() {
    if (!choice) return;
    setOpening(true);
    setError("");
    try {
      await onSelect(choice);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The saved version could not be opened.");
    } finally {
      setOpening(false);
    }
  }
  return (
    <fieldset className="saved-controls" disabled={disabled || opening}>
      <div className="field-row">
        <div className="field">
          <label htmlFor={testField}>{approvedOnly ? "Suite test" : "Saved test"}</label>
          <select id={testField} value={testId} onChange={(e) => {
            setTestId(e.target.value);
            setVersion("");
            setVersions([]);
            setError("");
          }}>
            <option value="">{loading ? "Loading tests…" : "Choose a test"}</option>
            {tests.map((t) => <option key={t.test_id} value={t.test_id}>{t.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={versionField}>{approvedOnly ? "Suite test version" : "Saved version"}</label>
          <select id={versionField} value={version} onChange={(e) => setVersion(e.target.value)} disabled={!versions.length}>
            <option value="">Choose a version</option>
            {[...versions].reverse().map((v) => (
              <option key={v.test_version} value={v.test_version}>
                Version {v.test_version} · {v.state}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && <p role="alert" className="error-text">
        {error} <button type="button" onClick={() => { setError(""); setRetry(retry + 1); }}>Reload saved tests</button>
      </p>}
      <button type="button" className="secondary-button" disabled={!choice} onClick={() => void selectVersion()}>
        {approvedOnly ? "Add to suite" : "Open version"}
      </button>
    </fieldset>
  );
}
