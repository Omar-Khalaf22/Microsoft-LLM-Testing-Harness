import { useCallback, useEffect, useRef, useState } from "react";

import {
  checkHealth, getExecution, getRun, getVersion, listHistory,
  type Attempt, type Execution, type RunResponse, type RunSummary, type SavedTestVersion,
} from "./api";
import EvidenceTransfer from "./EvidenceTransfer";
import HumanReviews from "./HumanReviews";
import RunComparison from "./RunComparison";
import RunForm from "./RunForm";
import RunResults from "./RunResults";
import { ExecutionProgress, RerunButton } from "./SavedExecution";
import SavedRuns from "./SavedRuns";
import SuiteRunner from "./SuiteRunner";

type HealthState = "checking" | "ok" | "unavailable";
type View = "configure" | "results" | "compare" | "suite";

function App() {
  const openSequence = useRef(0);
  const autoOpen = useRef<{ id: string; sequence: number } | null>(null);
  const [health, setHealth] = useState<HealthState>("checking");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRun, setSelectedRun] = useState<RunResponse | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<SavedTestVersion | null>(null);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [editorKey, setEditorKey] = useState(0);
  const [view, setView] = useState<View>("configure");
  const [compareSeed, setCompareSeed] = useState<string | undefined>();

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const saved = await listHistory(null, signal);
      if (!signal?.aborted) { setRuns(saved.items); setNextCursor(saved.next_cursor); }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setHistoryError(
        error instanceof Error ? error.message : "Could not load saved runs",
      );
    } finally {
      if (!signal?.aborted) setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        const isHealthy = await checkHealth(controller.signal);
        if (!controller.signal.aborted)
          setHealth(isHealthy ? "ok" : "unavailable");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setHealth("unavailable");
      }
    }

    void loadHealth();
    void refreshHistory(controller.signal);
    return () => controller.abort();
  }, [refreshHistory]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [view]);

  function handleRunCreated(run: RunResponse) {
    setRuns((previous) =>
      [run, ...previous.filter((item) => item.id !== run.id)],
    );
    setSelectedRun(run);
    setSelectedVersion(null);
    setEditorKey((previous) => previous + 1);
    setView("results");
  }

  const openRun = useCallback(async (id: string, resumeProgress = false) => {
    const sequence = ++openSequence.current;
    setHistoryError("");
    try {
      const saved = await getRun(id);
      if (sequence !== openSequence.current) return;
      setView("results");
      setSelectedRun(saved);
      setSelectedVersion(null);
      setEditorKey((previous) => previous + 1);
      if (resumeProgress && saved.metadata.execution_id &&
        (saved.status === "pending" || saved.status === "running")) {
        const plan = await getExecution(saved.metadata.execution_id);
        if (sequence === openSequence.current) {
          autoOpen.current = { id: plan.execution_id, sequence };
          setExecution(plan);
        }
      }
    } catch (error) {
      if (sequence === openSequence.current)
        setHistoryError(
          error instanceof Error
            ? error.message
            : "Could not open the saved run",
        );
    }
  }, []);
  const reservationSequence = openSequence.current;
  function onReserved(plan: Execution) {
    autoOpen.current = { id: plan.execution_id, sequence: reservationSequence };
    setExecution(plan);
    void refreshHistory();
  }
  const onExecutionFinished = useCallback((plan: Execution) => {
    void refreshHistory();
    const intent = autoOpen.current;
    if (intent?.id !== plan.execution_id) return;
    autoOpen.current = null;
    if (intent.sequence === openSequence.current && plan.attempts.length === 1)
      void openRun(plan.attempts[0].run_id);
  }, [openRun, refreshHistory]);
  const onOpenAttempt = (attempt: Attempt) => void openRun(attempt.run_id);

  async function loadMore() {
    if (!nextCursor || historyLoading) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const page = await listHistory(nextCursor);
      setRuns(previous => [...previous, ...page.items.filter(item => !previous.some(r => r.id === item.id))]);
      setNextCursor(page.next_cursor);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not load more runs");
    } finally { setHistoryLoading(false); }
  }

  function navigate(next: View) {
    openSequence.current += 1;
    setView(next);
  }

  function openComparison(seedId?: string) {
    setCompareSeed(seedId);
    navigate("compare");
  }

  function handleNewTest() {
    openSequence.current += 1;
    setView("configure");
    setSelectedRun(null);
    setSelectedVersion(null);
    setEditorKey((previous) => previous + 1);
  }

  function handleOpenVersion(version: SavedTestVersion) {
    openSequence.current += 1;
    setSelectedVersion(version);
    setSelectedRun(null);
    setEditorKey((previous) => previous + 1);
    setView("configure");
  }

  async function backToTest() {
    const m = selectedRun?.metadata;
    if (!m?.execution_id || !m.test_id || !m.test_version) {
      navigate("configure");
      return;
    }
    const sequence = ++openSequence.current;
    setHistoryError("");
    try {
      const version = await getVersion({ test_id: m.test_id, test_version: m.test_version });
      if (sequence === openSequence.current) handleOpenVersion(version);
    } catch (e) {
      if (sequence === openSequence.current)
        setHistoryError(e instanceof Error ? e.message : "The saved test could not be opened.");
    }
  }

  return (
    <div
      className={`app-shell ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}
    >
      <SavedRuns
        runs={runs}
        selectedRunId={selectedRun?.id}
        open={sidebarOpen}
        loading={historyLoading}
        error={historyError}
        onToggle={() => setSidebarOpen((open) => !open)}
        onRefresh={() => void refreshHistory()}
        onOpenRun={(run) => void openRun(run.id, true)}
        hasMore={!!nextCursor}
        onLoadMore={() => void loadMore()}
      />
      <main className="workspace">
        <header className="page-header">
          <div>
            <h1>LLM Testing Harness</h1>
            <p className="subtitle">
              Run prompts, evaluate responses, and inspect structured test
              results.
            </p>
          </div>
          <div className="header-actions">
            <button type="button" className="secondary-button" aria-pressed={view === "suite"}
              onClick={() => navigate("suite")}>Ordered suites</button>
            <button
              type="button"
              className="secondary-button"
              aria-pressed={view === "compare"}
              onClick={() => openComparison(selectedRun?.id)}
            >
              Compare runs
            </button>
            <div className="status" data-status={health}>
              <span className="status-dot" aria-hidden="true" />
              Backend {health === "ok" ? "ready" : health}
            </div>
          </div>
        </header>
        <EvidenceTransfer selectedRunId={selectedRun?.id} onImported={() => void refreshHistory()} />
        {execution && <ExecutionProgress key={execution.execution_id} initial={execution}
          onFinished={onExecutionFinished} onOpen={onOpenAttempt} />}
        <div className="workspace-views">
          <div hidden={view !== "configure"}>
            <RunForm
              key={editorKey}
              initialRun={selectedRun}
              initialVersion={selectedVersion}
              onNewTest={handleNewTest}
              onRunCreated={handleRunCreated}
              onOpenVersion={handleOpenVersion}
              onReserved={onReserved}
            />
          </div>
          <div hidden={view !== "results"}>
            <div className="result-actions">
              <button
                type="button"
                className="back-to-test"
                onClick={() => void backToTest()}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  focusable="false"
                >
                  <path d="m12 19-7-7 7-7M5 12h14" />
                </svg>
                Back to Test
              </button>
              {selectedRun && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => openComparison(selectedRun.id)}
                >
                  Compare with another run
                </button>
              )}
              {selectedRun?.metadata.execution_id &&
                (selectedRun.status === "completed" || selectedRun.status === "failed") && (
                  <RerunButton key={selectedRun.id} runId={selectedRun.id} onReserved={onReserved} />
                )}
            </div>
            <RunResults run={selectedRun} />
            {selectedRun && (
              <HumanReviews key={selectedRun.id} runId={selectedRun.id} />
            )}
          </div>
          {view === "compare" && (
            <RunComparison
              key={compareSeed ?? "none"}
              runs={runs}
              seedId={compareSeed}
              onBack={() => navigate(selectedRun ? "results" : "configure")}
            />
          )}
          {view === "suite" && <SuiteRunner onReserved={onReserved} onBack={() => navigate("configure")} />}
        </div>
      </main>
    </div>
  );
}

export default App;
