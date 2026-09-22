import { useEffect, useState } from "react";

import { fetchRunResults, type TestRunResult } from "./api";

type LoadState = "loading" | "loaded" | "error";

function formatScore(score: number, maxScore?: number): string {
  return maxScore === undefined ? `${score}` : `${score} / ${maxScore}`;
}

function RunCard({ run }: { run: TestRunResult }) {
  const { metrics } = run;

  return (
    <article className="run-card">
      <header className="run-card-header">
        <div>
          <h3>{run.testName ?? run.runId}</h3>
          {run.modelName && <p className="run-card-subtitle">{run.modelName}</p>}
        </div>
        <span className="status-badge" data-run-status={metrics.status}>
          {metrics.status}
        </span>
      </header>

      <section className="run-card-section">
        <h4>Response</h4>
        {run.response ? (
          <pre className="run-response">{run.response.content}</pre>
        ) : (
          <p className="muted">No response recorded.</p>
        )}
      </section>

      <section className="run-card-section">
        <h4>Evaluation</h4>
        {run.objectiveEvaluations.length === 0 && run.subjectiveEvaluations.length === 0 ? (
          <p className="muted">No evaluation results yet.</p>
        ) : (
          <ul className="evaluation-list">
            {run.objectiveEvaluations.map((evaluation) => (
              <li key={evaluation.criterionId}>
                <span>{evaluation.criterionLabel ?? evaluation.criterionId}</span>
                <span data-passed={evaluation.passed}>
                  {formatScore(evaluation.score, evaluation.maxScore)} ({evaluation.passed ? "passed" : "failed"})
                </span>
              </li>
            ))}
            {run.subjectiveEvaluations.map((evaluation) => (
              <li key={evaluation.criterionId}>
                <span>{evaluation.criterionLabel ?? evaluation.criterionId}</span>
                <span>
                  {formatScore(evaluation.score, evaluation.maxScore)}
                  {evaluation.notes ? ` — ${evaluation.notes}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="run-card-section">
        <h4>Run metrics</h4>
        <dl className="metrics-grid">
          {metrics.latencyMs !== undefined && (
            <>
              <dt>Latency</dt>
              <dd>{metrics.latencyMs} ms</dd>
            </>
          )}
          {metrics.promptTokens !== undefined && (
            <>
              <dt>Prompt tokens</dt>
              <dd>{metrics.promptTokens}</dd>
            </>
          )}
          {metrics.completionTokens !== undefined && (
            <>
              <dt>Completion tokens</dt>
              <dd>{metrics.completionTokens}</dd>
            </>
          )}
          {metrics.errorMessage && (
            <>
              <dt>Error</dt>
              <dd className="error-text">{metrics.errorMessage}</dd>
            </>
          )}
        </dl>
      </section>
    </article>
  );
}

function RunResults() {
  const [state, setState] = useState<LoadState>("loading");
  const [runs, setRuns] = useState<TestRunResult[]>([]);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function loadRuns() {
      setState("loading");
      try {
        const results = await fetchRunResults(controller.signal);
        setRuns(results);
        setState("loaded");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Unknown error");
        setState("error");
      }
    }

    void loadRuns();
    return () => controller.abort();
  }, [refreshToken]);

  return (
    <section className="run-results">
      <div className="run-results-header">
        <h2>Test run results</h2>
        <button type="button" onClick={() => setRefreshToken((token) => token + 1)}>
          Refresh
        </button>
      </div>

      {state === "loading" && <p className="muted">Loading run results…</p>}

      {state === "error" && (
        <p className="error-text">Could not load run results: {errorMessage}</p>
      )}

      {state === "loaded" && runs.length === 0 && (
        <p className="muted">No test runs yet.</p>
      )}

      {state === "loaded" && runs.length > 0 && (
        <div className="run-card-list">
          {runs.map((run) => (
            <RunCard key={run.runId} run={run} />
          ))}
        </div>
      )}
    </section>
  );
}

export default RunResults;
