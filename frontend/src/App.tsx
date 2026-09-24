import { useCallback, useEffect, useState } from "react";

import { checkHealth, listRuns, type RunResponse } from "./api";
import RunForm from "./RunForm";
import RunResults from "./RunResults";

type HealthState = "checking" | "ok" | "unavailable";

function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [selectedRun, setSelectedRun] = useState<RunResponse | null>(null);
  const [editorKey, setEditorKey] = useState(0);

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      setRuns(await listRuns(signal));
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

  function handleRunCreated(run: RunResponse) {
    setRuns((previous) => [run, ...previous]);
    setSelectedRun(run);
  }

  function handleUseTest(run: RunResponse) {
    setSelectedRun(run);
    setEditorKey((previous) => previous + 1);
  }

  function handleNewTest() {
    setSelectedRun(null);
    setEditorKey((previous) => previous + 1);
  }

  return (
    <main>
      <div className="page">
        <section className="status-card">
          <p className="eyebrow">Week 5 prototype</p>
          <h1>LLM Testing Harness</h1>
          <p>
            Backend status: <strong data-status={health}>{health}</strong>
          </p>
        </section>

        <RunForm
          key={editorKey}
          initialRun={selectedRun}
          onNewTest={handleNewTest}
          onRunCreated={handleRunCreated}
        />
        <RunResults
          runs={runs}
          loading={historyLoading}
          error={historyError}
          onRefresh={() => void refreshHistory()}
          onUseTest={handleUseTest}
        />
      </div>
    </main>
  );
}

export default App;
