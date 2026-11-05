import { useCallback, useEffect, useRef, useState } from "react";

import { checkHealth, getRun, listRuns, type RunResponse } from "./api";
import HumanReviews from "./HumanReviews";
import RunComparison from "./RunComparison";
import RunForm from "./RunForm";
import RunResults from "./RunResults";
import SavedRuns from "./SavedRuns";

type HealthState = "checking" | "ok" | "unavailable";

function App() {
  const openSequence = useRef(0);
  const [health, setHealth] = useState<HealthState>("checking");
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRun, setSelectedRun] = useState<RunResponse | null>(null);
  const [editorKey, setEditorKey] = useState(0);
  const [view, setView] = useState<"configure" | "results" | "compare">(
    "configure",
  );
  const [compareSeed, setCompareSeed] = useState<string | undefined>();

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const saved = await listRuns(signal);
      if (!signal?.aborted) setRuns(saved);
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
      [run, ...previous.filter((item) => item.id !== run.id)].slice(0, 100),
    );
    setSelectedRun(run);
    setEditorKey((previous) => previous + 1);
    setView("results");
  }

  async function handleOpenRun(run: RunResponse) {
    const sequence = ++openSequence.current;
    setHistoryError("");
    try {
      const saved = await getRun(run.id);
      if (sequence !== openSequence.current) return;
      setView("results");
      setSelectedRun(saved);
      setEditorKey((previous) => previous + 1);
    } catch (error) {
      if (sequence === openSequence.current)
        setHistoryError(
          error instanceof Error
            ? error.message
            : "Could not open the saved run",
        );
    }
  }

  function openComparison(seedId?: string) {
    setCompareSeed(seedId);
    setView("compare");
  }

  function handleNewTest() {
    openSequence.current += 1;
    setView("configure");
    setSelectedRun(null);
    setEditorKey((previous) => previous + 1);
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
        onOpenRun={handleOpenRun}
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
        <div className="workspace-views">
          <div hidden={view !== "configure"}>
            <RunForm
              key={editorKey}
              initialRun={selectedRun}
              onNewTest={handleNewTest}
              onRunCreated={handleRunCreated}
            />
          </div>
          <div hidden={view !== "results"}>
            <button
              type="button"
              className="back-to-test"
              onClick={() => setView("configure")}
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
              onBack={() => setView(selectedRun ? "results" : "configure")}
            />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
