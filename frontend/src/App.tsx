import { useEffect, useState } from "react";

import { checkHealth, type RunResponse } from "./api";
import RunForm from "./RunForm";
import RunResults from "./RunResults";

type HealthState = "checking" | "ok" | "unavailable";

function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [runs, setRuns] = useState<RunResponse[]>([]);

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
    return () => controller.abort();
  }, []);

  function handleRunCreated(run: RunResponse) {
    setRuns((previous) => [run, ...previous]);
  }

  return (
    <main>
      <div className="page">
        <section className="status-card">
          <p className="eyebrow">Phase 0 foundation</p>
          <h1>LLM Testing Harness</h1>
          <p>
            Backend status: <strong data-status={health}>{health}</strong>
          </p>
        </section>

        <RunForm onRunCreated={handleRunCreated} />
        <RunResults runs={runs} />
      </div>
    </main>
  );
}

export default App;
