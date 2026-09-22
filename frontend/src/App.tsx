import { useEffect, useState } from "react";

import { checkHealth } from "./api";
import RunResults from "./RunResults";

type HealthState = "checking" | "ok" | "unavailable";

function App() {
  const [health, setHealth] = useState<HealthState>("checking");

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

        <RunResults />
      </div>
    </main>
  );
}

export default App;
