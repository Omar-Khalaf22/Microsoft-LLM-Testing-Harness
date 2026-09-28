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
  const [formKey, setFormKey] = useState(0);
  const [activeTab, setActiveTab] = useState<"configure" | "result">("configure");

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const saved = await listRuns(100, signal);
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
    setFormKey((previous) => previous + 1);
    setActiveTab("result");
  }

  function handleOpenRun(run: RunResponse) {
    setSelectedRun(run);
    setFormKey((previous) => previous + 1);
    setActiveTab("result");
  }

  function handleNewTest() {
    setSelectedRun(null);
    setFormKey((previous) => previous + 1);
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
            <h1>LLM Testing Harness</h1>
            <p className="subtitle">
              Configure a test, run it against a model, and review its automated evaluation.
            </p>
          </div>
          <div className="status" data-status={health}>
            <span className="status-dot" aria-hidden="true" />
            Backend {health === "ok" ? "ready" : health}
          </div>
        </header>
        <div className="tab-bar" role="tablist" aria-label="Test workspace">
          <button
            type="button"
            role="tab"
            id="tab-configure"
            aria-selected={activeTab === "configure"}
            aria-controls="tabpanel-configure"
            className={`tab-button ${activeTab === "configure" ? "active" : ""}`}
            onClick={() => setActiveTab("configure")}
          >
            <span className="section-number">01</span> Configure test
          </button>
          <button
            type="button"
            role="tab"
            id="tab-result"
            aria-selected={activeTab === "result"}
            aria-controls="tabpanel-result"
            className={`tab-button ${activeTab === "result" ? "active" : ""}`}
            onClick={() => setActiveTab("result")}
          >
            <span className="section-number">02</span> Result
          </button>
        </div>
        <div className="tab-panel">
          <div
            id="tabpanel-configure"
            role="tabpanel"
            aria-labelledby="tab-configure"
            hidden={activeTab !== "configure"}
          >
            <RunForm
              key={formKey}
              initialRun={selectedRun}
              onNewTest={handleNewTest}
              onRunCreated={handleRunCreated}
            />
          </div>
          <div
            id="tabpanel-result"
            role="tabpanel"
            aria-labelledby="tab-result"
            hidden={activeTab !== "result"}
          >
            <RunResults run={selectedRun} />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
