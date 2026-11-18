import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
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
  // The editing controls stay hidden until the user starts a new suite or opens a saved one.
  const [editing, setEditing] = useState(false);
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
  // Reordering: drag an item's handle up or down (mouse, touch or pen), or focus the handle and
  // press the Up/Down arrow keys. Items swap places as the pointer passes their midpoints.
  const [dragKey, setDragKey] = useState<string | null>(null);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const keyboardFocus = useRef<string | null>(null);
  function move(key: string, direction: number) {
    const list = itemsRef.current;
    const index = list.findIndex((item) => item.key === key);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= list.length) return;
    const next = [...list];
    [next[index], next[target]] = [next[target], next[index]];
    itemsRef.current = next;
    changeItems(next);
  }
  useEffect(() => {
    if (!dragKey) return;
    const midpoint = (key?: string) => {
      const box = key ? rowRefs.current.get(key)?.getBoundingClientRect() : undefined;
      return box ? box.top + box.height / 2 : undefined;
    };
    const onMove = (event: PointerEvent) => {
      const list = itemsRef.current;
      const index = list.findIndex((item) => item.key === dragKey);
      if (index < 0) return;
      const above = midpoint(list[index - 1]?.key);
      const below = midpoint(list[index + 1]?.key);
      if (above !== undefined && event.clientY < above) move(dragKey, -1);
      else if (below !== undefined && event.clientY > below) move(dragKey, 1);
    };
    const end = () => setDragKey(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
    };
  }, [dragKey]);
  useEffect(() => {
    const key = keyboardFocus.current;
    if (!key) return;
    keyboardFocus.current = null;
    rowRefs.current.get(key)?.querySelector<HTMLButtonElement>(".drag-handle")?.focus();
  }, [items]);
  function onHandleKey(event: KeyboardEvent<HTMLButtonElement>, key: string) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    keyboardFocus.current = key;
    move(key, event.key === "ArrowUp" ? -1 : 1);
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
    setEditing(true);
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
    setEditing(true);
  }
  return (
    <section className="panel run-form">
      <div className="run-form-heading">
        <h2>Ordered Suites</h2>
        <button type="button" className="secondary-button" onClick={onBack}>Back to Tests</button>
      </div>
      <fieldset className="saved-controls" disabled={busy}>
        <button type="button" className="secondary-button new-suite-button" onClick={newSuite}>New Suite</button>
        <div className="suite-select-row">
          <label className="field">
            <span>Saved Suite</span>
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Choose a Suite</option>
              {suites.map((s) => <option key={s.suite_id} value={s.suite_id}>
                {s.name} · revision {s.suite_revision}
              </option>)}
            </select>
          </label>
          <button type="button" className="secondary-button" disabled={!selected}
            onClick={() => void edit(open)}>Open Suite</button>
        </div>
        {editing && <>
        <label className="field">
          <span>Suite Name</span>
          <input maxLength={100} value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        </label>
        <SavedTestPicker approvedOnly disabled={items.length >= 100}
          onSelect={(version) => changeItems([...items, asItem(version)])} />
        {items.length > 0 && <ol className={`suite-items${dragKey ? " dragging" : ""}`} aria-label="Ordered suite items">
          {items.map((item, i) => <li key={item.key}
            className={item.key === dragKey ? "drag-active" : undefined}
            ref={(node) => { if (node) rowRefs.current.set(item.key, node); else rowRefs.current.delete(item.key); }}>
            <div className={`suite-item-title${items.length > 1 ? " draggable" : ""}`}
              onPointerDown={(event) => {
                // Pressing anywhere on the row's name or grip starts a drag; the trash button does not.
                if (items.length < 2 || event.button !== 0) return;
                if ((event.target as HTMLElement).closest(".remove-item")) return;
                event.preventDefault();
                setDragKey(item.key);
              }}>
              <button type="button" className="drag-handle"
                disabled={items.length < 2}
                title="Drag up or down to reorder"
                aria-label={`Reorder ${item.name}, item ${i + 1} of ${items.length}: drag up or down, or press the Up or Down arrow key`}
                onKeyDown={(event) => onHandleKey(event, item.key)}>
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false" fill="currentColor">
                  {[4, 8, 12].map((y) => [5.5, 10.5].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.4" />))}
                </svg>
              </button>
              <strong>{item.name} · version {item.test.test_version}</strong>
              <button type="button" className="icon-button remove-item"
                title={`Remove ${item.name} from the suite`}
                aria-label={`Remove item ${i + 1}: ${item.name}`}
                onClick={() => changeItems(items.filter((_, j) => j !== i))}>
                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"
                  fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
                </svg>
              </button>
            </div>
          </li>)}
        </ol>}
        <button type="button" className="secondary-button" disabled={!name.trim() || !items.length || !dirty}
          onClick={() => void edit(save)}>Save Suite</button>
        {saved && !dirty && <p role="status">Saved suite revision {saved.suite_revision}</p>}
        </>}
      </fieldset>
      {error && <p role="alert" className="error-text">{error}</p>}
      {saved && !dirty && <section className="saved-execution" aria-label="Run saved suite">
        <ProfilePicker label="Suite Target Profile" value={profile} onChange={setProfile} disabled={busy} />
        {reservationError && <p role="alert" className="error-text">{reservationError}</p>}
        <button type="button" className="primary-button" disabled={!profile || busy}
          onClick={() => void start({
            suite: { suite_id: saved.suite_id, suite_revision: saved.suite_revision },
            profile_ids: [profile],
          })}>Run Suite</button>
      </section>}
    </section>
  );
}
