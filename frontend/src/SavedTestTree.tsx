import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { getSuite, listSuites, listTests, listVersions } from "./api";
import type { RunSummary, SavedSuite, SuiteSummary, TestReference } from "./api";
import { capitalize } from "./titleCase";

type TestInfo = Awaited<ReturnType<typeof listTests>>[number];
type VersionInfo = Awaited<ReturnType<typeof listVersions>>[number];
interface SuiteEntry {
  summary: SuiteSummary;
  detail: SavedSuite | null;
  error: string;
}
interface Structure {
  suites: SuiteEntry[];
  tests: TestInfo[];
}
interface VersionsState {
  status: "loading" | "ready" | "error";
  items: VersionInfo[];
  error: string;
}

interface VersionNode {
  key: string;
  number: number;
  state?: string;
  runs: RunSummary[];
  pinnedAt: number[];
  latest: boolean;
}
interface TestNode {
  key: string;
  testId: string;
  name: string;
  state?: string;
  versions: VersionNode[];
  runCount: number;
  lastRunAt: number;
  latestVersion?: number;
  versionsStatus?: VersionsState["status"];
  versionsError: string;
}
interface SuiteNode {
  key: string;
  entry: SuiteEntry;
  tests: TestNode[];
  runCount: number;
  lastRunAt: number;
}
interface Candidate {
  id: string;
  kind: "suite" | "test" | "version" | "run";
  label: string;
  detail: string;
  haystack: string;
  nameText: string;
  version?: number;
  runNumber?: number;
  open: string[];
  focus: string;
  run?: RunSummary;
}

// Past this many saved tests the tree starts collapsed so it does not fan out one request
// per test on load; versions are only fetched for tests the user actually opens.
const AUTO_OPEN_TEST_LIMIT = 25;

const timeOf = (value: string) => {
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
};
const formatDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};
const newestFirst = (a: RunSummary, b: RunSummary) =>
  timeOf(b.created_at) - timeOf(a.created_at) || b.id.localeCompare(a.id);
const scoreText = (run: RunSummary) =>
  run.score === null ? "Score unavailable" : `${run.score.toFixed(2)}/100`;
const count = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const MAX_SUGGESTIONS = 8;
const KIND_LABEL: Record<Candidate["kind"], string> = {
  suite: "Suite",
  test: "Test",
  version: "Version",
  run: "Run",
};
const KIND_ORDER: Record<Candidate["kind"], number> = { suite: 0, test: 0, version: 1, run: 2 };

// Run 1 is the oldest run of a version. The server numbers every run; runs created in this
// session arrive without a number, so they continue from the last numbered run before them.
function numberRuns(runs: RunSummary[]) {
  const numbers = new Map<string, number>();
  let last = 0;
  for (const run of [...runs].sort((a, b) => -newestFirst(a, b))) {
    last = run.metadata.run_number ?? last + 1;
    numbers.set(run.id, last);
  }
  return numbers;
}

// "login v2 run 3" -> name text "login", version 2, run 3. Typing only "run" or "version"
// narrows suggestions to that kind.
function parseQuery(raw: string) {
  let text = ` ${raw.toLowerCase().trim()} `;
  let version: number | undefined;
  let run: number | undefined;
  text = text.replace(/\s(?:version|ver|v)\s*(\d+)(?=\s)/, (_, n) => {
    version = Number(n);
    return " ";
  });
  text = text.replace(/\s(?:run|r|#)\s*(\d+)(?=\s)/, (_, n) => {
    run = Number(n);
    return " ";
  });
  const tokens = text.split(/\s+/).filter(Boolean);
  return { tokens, version, run };
}

function matchCandidates(candidates: Candidate[], raw: string): Candidate[] {
  const { tokens, version, run } = parseQuery(raw);
  if (!tokens.length && version === undefined && run === undefined) return [];
  const scored: { c: Candidate; score: number; index: number }[] = [];
  candidates.forEach((c, index) => {
    if (version !== undefined && (c.kind === "suite" || c.kind === "test" || c.version !== version))
      return;
    if (run !== undefined && (c.kind !== "run" || c.runNumber !== run)) return;
    if (!tokens.every((t) => c.haystack.includes(t))) return;
    const text = tokens.join(" ");
    const name = c.nameText;
    const score = !text
      ? 0
      : name.startsWith(text)
        ? 0
        : name.split(/[^a-z0-9]+/).some((w) => w.startsWith(tokens[0]))
          ? 1
          : 2;
    scored.push({ c, score, index });
  });
  scored.sort(
    (a, b) =>
      a.score - b.score || KIND_ORDER[a.c.kind] - KIND_ORDER[b.c.kind] || a.index - b.index,
  );
  return scored.map((s) => s.c);
}

const byActivity = <T extends { lastRunAt: number }>(a: T, b: T, nameA: string, nameB: string) =>
  b.lastRunAt - a.lastRunAt || nameA.localeCompare(nameB);

function Branch({
  open,
  onToggle,
  label,
  meta,
  badges,
  actions,
  children,
  className = "",
  treeKey,
  flash = false,
}: {
  open: boolean;
  onToggle: () => void;
  label: string;
  meta: string;
  badges?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  treeKey?: string;
  flash?: boolean;
}) {
  const panel = useId();
  return (
    <li className={`tree-node ${className}${flash ? " tree-flash" : ""}`} data-tree-key={treeKey}>
      <div className="tree-row">
        <button
          type="button"
          className="tree-toggle"
          aria-expanded={open}
          aria-controls={panel}
          onClick={onToggle}
        >
          <span className="tree-chevron" aria-hidden="true" />
          <span className="tree-label">
            {label}
            {badges}
          </span>
          <span className="tree-meta">{meta}</span>
        </button>
        {actions}
      </div>
      <ul id={panel} className="tree-children" hidden={!open}>
        {children}
      </ul>
    </li>
  );
}

function RunLeaf({
  run,
  number,
  selected,
  flash,
  onOpenRun,
}: {
  run: RunSummary;
  number?: number;
  selected: boolean;
  flash: boolean;
  onOpenRun: (run: RunSummary) => void;
}) {
  const name = run.metadata.test_name || "Untitled test";
  return (
    <li className={flash ? "tree-flash" : undefined} data-tree-key={`r:${run.id}`}>
      <button
        type="button"
        className="saved-run-item tree-run"
        data-run-id={run.id}
        aria-pressed={selected}
        aria-label={`Load ${name}, ${number ? `Run ${number}, ` : ""}run from ${formatDate(run.created_at)}`}
        onClick={() => onOpenRun(run)}
      >
        <span className="saved-run-details">
          {number !== undefined && <strong className="tree-run-number">Run {number}</strong>}
          {number !== undefined && " · "}
          {formatDate(run.created_at)} · {scoreText(run)}
        </span>
        <span className="tree-run-sub">
          Version {run.metadata.test_version ?? "imported"} · {run.model}
          {run.status !== "completed" ? ` · ${capitalize(run.status)}` : ""}
          {run.metadata.rerun_of_run_id ? " · rerun" : ""}
        </span>
      </button>
    </li>
  );
}

export default function SavedTestTree({
  runs,
  selectedRunId,
  hasMore,
  reloadKey,
  onOpenRun,
  onOpenVersion,
}: {
  runs: RunSummary[];
  selectedRunId?: string;
  hasMore: boolean;
  reloadKey: number;
  onOpenRun: (run: RunSummary) => void;
  onOpenVersion?: (version: TestReference) => Promise<void> | void;
}) {
  const [structure, setStructure] = useState<Structure | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [autoReload, setAutoReload] = useState(0);
  const [versions, setVersions] = useState<Record<string, VersionsState>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [opening, setOpening] = useState("");
  const [actionError, setActionError] = useState("");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [flash, setFlash] = useState("");
  const [focusTarget, setFocusTarget] = useState<{ key: string; n: number } | null>(null);
  const searchId = useId();
  const treeRef = useRef<HTMLDivElement>(null);
  const requested = useRef(new Set<string>());
  const revealed = useRef<string | undefined>(undefined);
  const triedUnknown = useRef("");

  useEffect(() => {
    const controller = new AbortController();
    requested.current.clear();
    setLoading(true);
    setError("");
    (async () => {
      try {
        const [suites, tests] = await Promise.all([
          listSuites(controller.signal),
          listTests(controller.signal),
        ]);
        const entries = await Promise.all(
          suites.map(async (summary): Promise<SuiteEntry> => {
            try {
              return { summary, detail: await getSuite(summary), error: "" };
            } catch (e) {
              return {
                summary,
                detail: null,
                error: e instanceof Error ? e.message : "This suite could not be loaded",
              };
            }
          }),
        );
        if (controller.signal.aborted) return;
        setStructure({ suites: entries, tests });
        setVersions({});
      } catch (e) {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Saved tests could not be loaded");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [reloadKey, retry, autoReload]);

  const loadVersions = useCallback((testId: string) => {
    if (requested.current.has(testId)) return;
    requested.current.add(testId);
    setVersions((previous) => ({
      ...previous,
      [testId]: { status: "loading", items: previous[testId]?.items ?? [], error: "" },
    }));
    listVersions(testId)
      .then((items) => setVersions((p) => ({ ...p, [testId]: { status: "ready", items, error: "" } })))
      .catch((e) =>
        setVersions((p) => ({
          ...p,
          [testId]: {
            status: "error",
            items: p[testId]?.items ?? [],
            error: e instanceof Error ? e.message : "Versions could not be loaded",
          },
        })),
      );
  }, []);

  const model = useMemo(() => {
    const smallTree = (structure?.tests.length ?? 0) <= AUTO_OPEN_TEST_LIMIT;
    const byVersion = new Map<string, RunSummary[]>();
    const byTest = new Map<string, RunSummary[]>();
    const imported: RunSummary[] = [];
    for (const run of runs) {
      const { test_id: testId, test_version: version } = run.metadata;
      if (!testId || version === undefined) {
        imported.push(run);
        continue;
      }
      byTest.set(testId, [...(byTest.get(testId) ?? []), run]);
      const key = `${testId}#${version}`;
      byVersion.set(key, [...(byVersion.get(key) ?? []), run]);
    }
    for (const list of [...byVersion.values(), ...byTest.values(), imported]) list.sort(newestFirst);

    const numbers = new Map<string, number>();
    for (const list of byVersion.values())
      numberRuns(list).forEach((n, id) => numbers.set(id, n));

    const info = new Map<string, TestInfo>((structure?.tests ?? []).map((t) => [t.test_id, t]));
    const allKeys: string[] = [];
    const openTests = new Set<string>();
    const defaultOpen = new Map<string, boolean>();

    function buildTest(scope: string, testId: string, pinned: Map<number, number[]>): TestNode {
      const known = info.get(testId);
      const runsOfTest = byTest.get(testId) ?? [];
      const fetched = versions[testId];
      const numbers = new Set<number>(pinned.keys());
      for (const v of fetched?.items ?? []) numbers.add(v.test_version);
      for (const run of runsOfTest) numbers.add(run.metadata.test_version as number);
      if (known) numbers.add(known.latest_version);
      const latestVersion = numbers.size ? Math.max(...numbers) : undefined;
      const key = `t:${scope}:${testId}`;
      const nodes: VersionNode[] = [...numbers]
        .sort((a, b) => b - a)
        .map((number) => {
          const vKey = `v:${scope}:${testId}:${number}`;
          const state =
            fetched?.items.find((v) => v.test_version === number)?.state ??
            (known && known.latest_version === number ? known.state : undefined);
          const node: VersionNode = {
            key: vKey,
            number,
            state,
            runs: byVersion.get(`${testId}#${number}`) ?? [],
            pinnedAt: pinned.get(number) ?? [],
            latest: number === latestVersion,
          };
          allKeys.push(vKey);
          return node;
        });
      // Open the newest version that actually has runs (a newer empty draft would otherwise hide
      // them), plus any version the suite pins.
      const newestWithRuns = nodes.find((v) => v.runs.length > 0);
      for (const v of nodes)
        defaultOpen.set(v.key, v === newestWithRuns || v.pinnedAt.length > 0);
      allKeys.push(key);
      defaultOpen.set(key, smallTree);
      return {
        key,
        testId,
        name: known?.name ?? runsOfTest[0]?.metadata.test_name ?? testId,
        state: known?.state,
        versions: nodes,
        runCount: runsOfTest.length,
        lastRunAt: runsOfTest.length ? timeOf(runsOfTest[0].created_at) : 0,
        latestVersion,
        versionsStatus: fetched?.status,
        versionsError: fetched?.error ?? "",
      };
    }

    const inSuite = new Set<string>();
    const suites: SuiteNode[] = (structure?.suites ?? []).map((entry) => {
      const key = `s:${entry.summary.suite_id}`;
      const order: string[] = [];
      const pins = new Map<string, Map<number, number[]>>();
      (entry.detail?.items ?? []).forEach((item, index) => {
        inSuite.add(item.test_id);
        if (!pins.has(item.test_id)) {
          pins.set(item.test_id, new Map());
          order.push(item.test_id);
        }
        const forTest = pins.get(item.test_id)!;
        forTest.set(item.test_version, [...(forTest.get(item.test_version) ?? []), index + 1]);
      });
      const tests = order.map((id) => buildTest(key, id, pins.get(id)!));
      allKeys.push(key);
      defaultOpen.set(key, true);
      return {
        key,
        entry,
        tests,
        runCount: tests.reduce((sum, t) => sum + t.runCount, 0),
        lastRunAt: Math.max(0, ...tests.map((t) => t.lastRunAt)),
      };
    });
    suites.sort((a, b) => byActivity(a, b, a.entry.summary.name, b.entry.summary.name));

    const loose = new Set<string>();
    for (const t of structure?.tests ?? []) if (!inSuite.has(t.test_id)) loose.add(t.test_id);
    for (const id of byTest.keys()) if (!inSuite.has(id)) loose.add(id);
    const free = [...loose]
      .map((id) => buildTest("free", id, new Map()))
      .sort((a, b) => byActivity(a, b, a.name, b.name));

    // Open nodes need their version list; only those are fetched.
    const wanted = new Set<string>();
    const isOpen = (key: string) => (key in open ? open[key] : (defaultOpen.get(key) ?? false));
    for (const s of suites) if (isOpen(s.key)) for (const t of s.tests) if (isOpen(t.key)) wanted.add(t.testId);
    for (const t of free) if (isOpen(t.key)) wanted.add(t.testId);
    wanted.forEach((id) => openTests.add(id));

    const pathFor = (runId: string): string[] | null => {
      for (const s of suites)
        for (const t of s.tests)
          for (const v of t.versions)
            if (v.runs.some((r) => r.id === runId)) return [s.key, t.key, v.key];
      for (const t of free)
        for (const v of t.versions) if (v.runs.some((r) => r.id === runId)) return [t.key, v.key];
      return imported.some((r) => r.id === runId) ? ["imported"] : null;
    };
    const unknown = [...byTest.keys()].filter((id) => !info.has(id)).sort();
    return { suites, free, imported, allKeys, openTests, isOpen, pathFor, unknown, numbers };
  }, [structure, runs, versions, open]);

  useEffect(() => {
    model.openTests.forEach(loadVersions);
  }, [model.openTests, loadVersions]);

  // A run for a test the structure has not seen yet (just created elsewhere) triggers one reload.
  const unknownKey = model.unknown.join(",");
  useEffect(() => {
    if (!unknownKey || loading || !structure || triedUnknown.current === unknownKey) return;
    triedUnknown.current = unknownKey;
    setAutoReload((n) => n + 1);
  }, [unknownKey, loading, structure]);

  // Keep the selected run visible by opening its branch, once per selection.
  useEffect(() => {
    if (!selectedRunId || revealed.current === selectedRunId) return;
    const path = model.pathFor(selectedRunId);
    if (!path) return;
    revealed.current = selectedRunId;
    setOpen((previous) => ({ ...previous, ...Object.fromEntries(path.map((key) => [key, true])) }));
  }, [selectedRunId, model]);

  const candidates = useMemo(() => {
    const out: Candidate[] = [];
    const seenRuns = new Set<string>();
    const addTest = (test: TestNode, suite?: SuiteNode) => {
      const where = suite ? suite.entry.summary.name : "Not in a suite";
      const base = [...(suite ? [suite.key] : []), test.key];
      const nameText = test.name.toLowerCase();
      const context = `${where} ${test.name}`.toLowerCase();
      out.push({
        id: `t|${test.key}`,
        kind: "test",
        label: test.name,
        detail: `${where} · ${count(test.runCount, "run")}`,
        haystack: `test ${context}`,
        nameText,
        open: base,
        focus: test.key,
      });
      for (const v of test.versions) {
        out.push({
          id: `v|${v.key}`,
          kind: "version",
          label: `${test.name} · Version ${v.number}`,
          detail: `${where} · ${count(v.runs.length, "run")}`,
          haystack: `version v${v.number} ${v.number} ${context}`,
          nameText,
          version: v.number,
          open: base,
          focus: v.key,
        });
        for (const run of v.runs) {
          if (seenRuns.has(run.id)) continue;
          seenRuns.add(run.id);
          const n = model.numbers.get(run.id);
          out.push({
            id: `r|${run.id}`,
            kind: "run",
            label: `${test.name} · Version ${v.number} · Run ${n}`,
            detail: `${formatDate(run.created_at)} · ${scoreText(run)} · ${where}`,
            haystack: `run r${n} ${n} version v${v.number} ${v.number} ${context} ${formatDate(
              run.created_at,
            ).toLowerCase()}`,
            nameText,
            version: v.number,
            runNumber: n,
            open: [...base, v.key],
            focus: `r:${run.id}`,
            run,
          });
        }
      }
    };
    for (const suite of model.suites) {
      const name = suite.entry.summary.name;
      out.push({
        id: `s|${suite.key}`,
        kind: "suite",
        label: name,
        detail: `Revision ${suite.entry.summary.suite_revision} · ${count(suite.tests.length, "test")}`,
        haystack: `suite ${name.toLowerCase()}`,
        nameText: name.toLowerCase(),
        open: [],
        focus: suite.key,
      });
      for (const test of suite.tests) addTest(test, suite);
    }
    for (const test of model.free) addTest(test);
    for (const run of model.imported) {
      const name = run.metadata.test_name || "Untitled test";
      out.push({
        id: `r|${run.id}`,
        kind: "run",
        label: `${name} · imported run`,
        detail: `${formatDate(run.created_at)} · ${scoreText(run)}`,
        haystack: `run imported ${name.toLowerCase()} ${formatDate(run.created_at).toLowerCase()}`,
        nameText: name.toLowerCase(),
        open: ["imported"],
        focus: `r:${run.id}`,
        run,
      });
    }
    return out;
  }, [model]);

  const suggestions = useMemo(() => matchCandidates(candidates, query), [candidates, query]);
  const shown = suggestions.slice(0, MAX_SUGGESTIONS);
  const listId = `${searchId}-list`;
  const optionId = (index: number) => `${searchId}-opt-${index}`;
  const searching = query.trim().length > 0;

  // After a suggestion is chosen the branch opens, then it scrolls into view and flashes once.
  useEffect(() => {
    if (!focusTarget) return;
    const el = treeRef.current?.querySelector(
      `[data-tree-key="${CSS.escape(focusTarget.key)}"]`,
    );
    if (el) el.scrollIntoView({ block: "nearest" });
    setFlash(focusTarget.key);
    const timer = window.setTimeout(() => setFlash(""), 1800);
    return () => window.clearTimeout(timer);
  }, [focusTarget]);

  function choose(candidate: Candidate) {
    setOpen((previous) => ({
      ...previous,
      ...Object.fromEntries(candidate.open.map((key) => [key, true])),
      ...(candidate.kind === "suite" ? { [candidate.focus]: true } : {}),
    }));
    setFocusTarget((previous) => ({ key: candidate.focus, n: (previous?.n ?? 0) + 1 }));
    setSearchOpen(false);
    if (candidate.run) {
      revealed.current = candidate.run.id;
      onOpenRun(candidate.run);
    }
  }

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!shown.length) return;
      event.preventDefault();
      setSearchOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => (index + step + shown.length) % shown.length);
    } else if (event.key === "Enter") {
      if (searchOpen && shown[active]) {
        event.preventDefault();
        choose(shown[active]);
      }
    } else if (event.key === "Escape") {
      if (searchOpen) {
        event.preventDefault();
        setSearchOpen(false);
      } else if (query) {
        event.preventDefault();
        setQuery("");
      }
    }
  }

  const toggle = (key: string) =>
    setOpen((previous) => ({ ...previous, [key]: !model.isOpen(key) }));
  const setAll = (value: boolean) =>
    setOpen(Object.fromEntries([...model.allKeys, "imported"].map((key) => [key, value])));

  async function openVersion(ref: TestReference) {
    if (!onOpenVersion) return;
    const id = `${ref.test_id}#${ref.test_version}`;
    setOpening(id);
    setActionError("");
    try {
      await onOpenVersion(ref);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "The saved version could not be opened.");
    } finally {
      setOpening("");
    }
  }

  function renderTest(test: TestNode, scope: "suite" | "free") {
    return (
      <Branch
        key={test.key}
        treeKey={test.key}
        flash={flash === test.key}
        className="level-test"
        open={model.isOpen(test.key)}
        onToggle={() => toggle(test.key)}
        label={test.name}
        badges={
          test.state === "historical" ? <span className="tree-badge">Historical</span> : null
        }
        meta={`${test.latestVersion ? `Latest version ${test.latestVersion} · ` : ""}${count(test.runCount, "run")}`}
      >
        {test.versionsStatus === "loading" && test.versions.length === 0 && (
          <li className="tree-note" role="status">
            Loading versions…
          </li>
        )}
        {test.versionsStatus === "error" && (
          <li className="tree-note" role="alert">
            Versions could not be loaded: {test.versionsError}
          </li>
        )}
        {test.versions.map((v) => {
          const id = `${test.testId}#${v.number}`;
          return (
            <Branch
              key={v.key}
              treeKey={v.key}
              flash={flash === v.key}
              className="level-version"
              open={model.isOpen(v.key)}
              onToggle={() => toggle(v.key)}
              label={`Version ${v.number}`}
              badges={
                <>
                  {v.latest && <span className="tree-badge">Latest</span>}
                  {scope === "suite" && v.pinnedAt.length > 0 && (
                    <span className="tree-badge pinned">Pinned in suite</span>
                  )}
                  {v.state && v.state !== "approved" && <span className="tree-badge">{capitalize(v.state)}</span>}
                </>
              }
              meta={`${v.state === "approved" ? "Approved · " : ""}${count(v.runs.length, "run")}${
                scope === "suite" && v.pinnedAt.length
                  ? ` · position ${v.pinnedAt.join(", ")}`
                  : ""
              }`}
              actions={
                onOpenVersion && (
                  <button
                    type="button"
                    className="tree-action"
                    disabled={opening === id}
                    aria-label={`Open ${test.name} version ${v.number} in the editor`}
                    onClick={() => void openVersion({ test_id: test.testId, test_version: v.number })}
                  >
                    {opening === id ? "Opening…" : "Open"}
                  </button>
                )
              }
            >
              {v.runs.length === 0 ? (
                <li className="tree-note">No runs yet.</li>
              ) : (
                v.runs.map((run) => (
                  <RunLeaf
                    key={run.id}
                    run={run}
                    number={model.numbers.get(run.id)}
                    selected={run.id === selectedRunId}
                    flash={flash === `r:${run.id}`}
                    onOpenRun={onOpenRun}
                  />
                ))
              )}
            </Branch>
          );
        })}
        {test.versions.length === 0 && test.versionsStatus === "ready" && (
          <li className="tree-note">No saved versions.</li>
        )}
      </Branch>
    );
  }

  const empty =
    !!structure && !model.suites.length && !model.free.length && !model.imported.length;

  if (loading && !structure)
    return (
      <p className="sidebar-empty" role="status">
        Loading saved tests…
      </p>
    );
  if (error && !structure)
    return (
      <p className="sidebar-error" role="alert">
        Could not load saved tests: {error}{" "}
        <button type="button" className="tree-action" onClick={() => setRetry((n) => n + 1)}>
          Retry
        </button>
      </p>
    );
  if (empty)
    return (
      <p className="sidebar-empty">
        No saved tests yet. Save a test or run an evaluation and it will appear here with its
        suites, versions and runs.
      </p>
    );

  return (
    <div className="saved-tree" aria-busy={loading} ref={treeRef}>
      <div className="tree-search">
        <label className="tree-search-label" htmlFor={`${searchId}-input`}>
          Search Saved Tests
        </label>
        <div className="tree-search-box">
          <input
            id={`${searchId}-input`}
            type="search"
            role="combobox"
            className="tree-search-input"
            placeholder="Test, version or run, e.g. login v2 run 3"
            autoComplete="off"
            spellCheck={false}
            value={query}
            aria-expanded={searchOpen && searching}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={searchOpen && shown[active] ? optionId(active) : undefined}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
              setSearchOpen(true);
            }}
            onFocus={() => setSearchOpen(true)}
            onBlur={() => setSearchOpen(false)}
            onKeyDown={onSearchKeyDown}
          />
          {query && (
            <button
              type="button"
              className="tree-search-clear"
              aria-label="Clear search"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                setQuery("");
                setActive(0);
              }}
            >
              ×
            </button>
          )}
        </div>
        <ul
          id={listId}
          role="listbox"
          aria-label="Search suggestions"
          className="tree-suggestions"
          hidden={!(searchOpen && searching)}
        >
          {shown.map((candidate, index) => (
            <li
              key={candidate.id}
              id={optionId(index)}
              role="option"
              aria-selected={index === active}
              className={`tree-suggestion${index === active ? " active" : ""}`}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(candidate)}
            >
              <span className={`tree-kind kind-${candidate.kind}`}>{KIND_LABEL[candidate.kind]}</span>
              <span className="tree-suggestion-text">
                <span className="tree-suggestion-label">{candidate.label}</span>
                <span className="tree-suggestion-detail">{candidate.detail}</span>
              </span>
            </li>
          ))}
        </ul>
        {searching && (
          <p className="tree-search-status" role="status">
            {suggestions.length === 0
              ? `No saved test, version or run matches “${query.trim()}”.`
              : `${count(suggestions.length, "match")}${
                  suggestions.length > shown.length ? `, showing ${shown.length}` : ""
                }.`}
            {hasMore && " Only loaded runs are searched; use Load More Runs for older ones."}
          </p>
        )}
      </div>
      <div className="tree-toolbar">
        <button type="button" className="tree-action" onClick={() => setAll(true)}>
          Expand All
        </button>
        <button type="button" className="tree-action" onClick={() => setAll(false)}>
          Collapse All
        </button>
      </div>
      {error && (
        <p className="sidebar-error" role="alert">
          Could not refresh saved tests: {error}
        </p>
      )}
      {actionError && (
        <p className="sidebar-error" role="alert">
          {actionError}
        </p>
      )}

      <section aria-labelledby="tree-suites">
        <h3 id="tree-suites" className="tree-heading">
          Suites
        </h3>
        {model.suites.length === 0 ? (
          <p className="tree-note">No suites yet. Create one under “Ordered Suites”.</p>
        ) : (
          <ul className="tree-list">
            {model.suites.map((suite) => (
              <Branch
                key={suite.key}
                treeKey={suite.key}
                flash={flash === suite.key}
                className="level-suite"
                open={model.isOpen(suite.key)}
                onToggle={() => toggle(suite.key)}
                label={suite.entry.summary.name}
                meta={`Revision ${suite.entry.summary.suite_revision} · ${count(
                  suite.tests.length,
                  "test",
                )} · ${count(suite.runCount, "run")}`}
              >
                {suite.entry.error && (
                  <li className="tree-note" role="alert">
                    This suite could not be loaded: {suite.entry.error}
                  </li>
                )}
                {suite.tests.map((test) => renderTest(test, "suite"))}
              </Branch>
            ))}
          </ul>
        )}
      </section>

      {(model.free.length > 0 || model.suites.length > 0) && (
        <section aria-labelledby="tree-free">
          <h3 id="tree-free" className="tree-heading">
            Tests Not in a Suite
          </h3>
          {model.free.length === 0 ? (
            <p className="tree-note">Every saved test belongs to a suite.</p>
          ) : (
            <ul className="tree-list">{model.free.map((test) => renderTest(test, "free"))}</ul>
          )}
        </section>
      )}

      {model.imported.length > 0 && (
        <section aria-labelledby="tree-imported">
          <h3 id="tree-imported" className="tree-heading">
            Imported Runs
          </h3>
          <ul className="tree-list">
            <Branch
              className="level-test"
              open={model.isOpen("imported")}
              onToggle={() => toggle("imported")}
              label="Not linked to a saved test"
              meta={count(model.imported.length, "run")}
            >
              {model.imported.map((run) => (
                <RunLeaf
                  key={run.id}
                  run={run}
                  selected={run.id === selectedRunId}
                  flash={flash === `r:${run.id}`}
                  onOpenRun={onOpenRun}
                />
              ))}
            </Branch>
          </ul>
        </section>
      )}

      {hasMore && (
        <p className="tree-note">
          Only the most recent runs are loaded, so older runs are not shown under their versions
          yet.
        </p>
      )}
    </div>
  );
}
