import { useEffect, useState } from "react";

type HealthState = "checking" | "ok" | "unavailable";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function App() {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    async function checkBackend() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, {
          signal: controller.signal,
        });
        const body: unknown = await response.json();
        const isHealthy =
          response.ok &&
          typeof body === "object" &&
          body !== null &&
          "status" in body &&
          body.status === "ok";

        setHealth(isHealthy ? "ok" : "unavailable");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setHealth("unavailable");
      }
    }

    void checkBackend();
    return () => controller.abort();
  }, []);

  return (
    <main>
      <section className="status-card">
        <p className="eyebrow">Phase 0 foundation</p>
        <h1>LLM Testing Harness</h1>
        <p>
          Backend status: <strong data-status={health}>{health}</strong>
        </p>
      </section>
    </main>
  );
}

export default App;

