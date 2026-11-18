import { useEffect, useState } from "react";
import { getSuite, getVersion, listSuites, saveSuite, testReference } from "./api";
import type { Execution, SavedSuite, SuiteSummary, TestReference } from "./api";
import { ProfilePicker, useReservation } from "./SavedExecution";
import SavedTestPicker from "./SavedTestPicker";

interface Item {
  key: string;
  test: TestReference;
  name: string;
}
const asItem = (version: TestReference & { name: string }): Item => ({
  key: crypto.randomUUID(), test: testReference(version), name: version.name,
});

export default function SuiteRunner({
  onReserved, onBack,
}: {
  onReserved: (execution: Execution) => void;
  onBack: () => void;
}) {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [saved, setSaved] = useState<SavedSuite | null>(null);
  const [name, setName] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [dirty, setDirty] = useState(false);
  const [working, setWorking] = useState(false);
  const [profile, setProfile] = useState("");
  const [error, setError] = useState("");
  const { reserving, error: reservationError, start } = useReservation(onReserved);
  const busy = working || reserving;
  useEffect(() => {
    const controller = new AbortController();
    listSuites(controller.signal)
      .then(setSuites)
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  function changeItems(next: Item[]) {
    setItems(next);
    setDirty(true);
  }
  function move(index: number, direction: number) {
    const next = [...items];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    changeItems(next);
  }
  async function edit(operation: () => Promise<void>) {
    setWorking(true);
    setError("");
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The suite could not be saved or opened.");
    } finally {
      setWorking(false);
    }
  }
  async function open() {
    const choice = suites.find((s) => s.suite_id === selected);
    if (!choice) return;
    const suite = await getSuite(choice);
    const versions = await Promise.all(suite.items.map((ref) => getVersion(ref)));
    setSaved(suite);
    setName(suite.name);
    setItems(versions.map(asItem));
    setDirty(false);
  }
  async function save() {
    const suite = await saveSuite(name.trim(), items.map((item) => item.test), saved);
    setSaved(suite);
    setSelected(suite.suite_id);
    setSuites((prior) => [...prior.filter((s) => s.suite_id !== suite.suite_id), suite]);
    setDirty(false);
  }
  function newSuite() {
    setSelected("");
    setSaved(null);
    setName("");
    setItems([]);
    setDirty(false);
    setError("");
  }
  return (
    <section className="panel run-form">
      <div className="run-form-heading">
        <h2>Ordered suites</h2>
        <button type="button" className="secondary-button" onClick={onBack}>Back to tests</button>
      </div>
      <fieldset className="saved-controls" disabled={busy}>
        <label className="field">
          <span>Saved suite</span>
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Choose a suite</option>
            {suites.map((s) => <option key={s.suite_id} value={s.suite_id}>
              {s.name} · revision {s.suite_revision}
            </option>)}
          </select>
        </label>
        <div className="saved-actions">
          <button type="button" className="secondary-button" disabled={!selected}
            onClick={() => void edit(open)}>Open suite</button>
          <button type="button" className="text-button" onClick={newSuite}>New suite</button>
        </div>
        <label className="field">
          <span>Suite name</span>
          <input maxLength={100} value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        </label>
        <SavedTestPicker approvedOnly disabled={items.length >= 100}
          onSelect={(version) => changeItems([...items, asItem(version)])} />
        {items.length > 0 && <ol className="suite-items" aria-label="Ordered suite items">
          {items.map((item, i) => <li key={item.key}>
            <strong>{item.name} · version {item.test.test_version}</strong>
            <div className="saved-actions">
              <button type="button" className="text-button" aria-label={`Move item ${i + 1} up`}
                disabled={i === 0} onClick={() => move(i, -1)}>Move up</button>
              <button type="button" className="text-button" aria-label={`Move item ${i + 1} down`}
                disabled={i === items.length - 1} onClick={() => move(i, 1)}>Move down</button>
              <button type="button" className="text-button" aria-label={`Remove item ${i + 1}`}
                onClick={() => changeItems(items.filter((_, j) => j !== i))}>Remove</button>
            </div>
          </li>)}
        </ol>}
        <button type="button" className="secondary-button" disabled={!name.trim() || !items.length || !dirty}
          onClick={() => void edit(save)}>Save suite</button>
        {saved && !dirty && <p role="status">Saved suite revision {saved.suite_revision}</p>}
      </fieldset>
      {error && <p role="alert" className="error-text">{error}</p>}
      {saved && !dirty && <section className="saved-execution" aria-label="Run saved suite">
        <ProfilePicker label="Suite target profile" value={profile} onChange={setProfile} disabled={busy} />
        {reservationError && <p role="alert" className="error-text">{reservationError}</p>}
        <button type="button" className="primary-button" disabled={!profile || busy}
          onClick={() => void start({
            suite: { suite_id: saved.suite_id, suite_revision: saved.suite_revision },
            profile_ids: [profile],
          })}>Run suite</button>
      </section>}
    </section>
  );
}
