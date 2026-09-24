import { useCallback, useEffect, useState } from "react";

import { checkHealth, listRuns, type RunResponse } from "./api";
import RunForm from "./RunForm";
import RunResults from "./RunResults";
import SavedRuns from "./SavedRuns";

type HealthState = "checking" | "ok" | "unavailable";

function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRun, setSelectedRun] = useState<RunResponse | null>(null);
  const [editorKey, setEditorKey] = useState(0);

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const saved = await listRuns(signal);
      if (!signal?.aborted) setRuns(saved);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setHistoryError(error instanceof Error ? error.message : "Could not load saved runs");
    } finally {
      if (!signal?.aborted) setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        const isHealthy = await checkHealth(controller.signal);
        if (!controller.signal.aborted) setHealth(isHealthy ? "ok" : "unavailable");
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

  function handleRunCreated(run: RunResponse) {
    setRuns((previous) => [run, ...previous.filter((item) => item.id !== run.id)].slice(0, 100));
    setSelectedRun(run);
    setEditorKey((previous) => previous + 1);
  }

  function handleOpenRun(run: RunResponse) {
    setSelectedRun(run);
    setEditorKey((previous) => previous + 1);
  }

  function handleNewTest() {
    setSelectedRun(null);
    setEditorKey((previous) => previous + 1);
  }

  return (
    <div className={`app-shell ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
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
            <p className="eyebrow">Capstone prototype</p>
            <h1>LLM Testing Harness</h1>
            <p className="subtitle">Run prompts, evaluate responses, and revisit saved results.</p>
          </div>
          <div className="status" data-status={health}>
            <span className="status-dot" aria-hidden="true" />
            Backend {health === "ok" ? "ready" : health}
          </div>
        </header>
        <div className="workspace-grid">
          <RunForm
            key={editorKey}
            initialRun={selectedRun}
            onNewTest={handleNewTest}
            onRunCreated={handleRunCreated}
          />
          <RunResults run={selectedRun} />
        </div>
      </main>
    </div>
  );
}

export default App;
