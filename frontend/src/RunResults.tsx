import type { RunResponse } from "./api";

function RunCard({
  run,
  onUseTest,
}: {
  run: RunResponse;
  onUseTest: (run: RunResponse) => void;
}) {
  const usage = run.metadata.usage;

  return (
    <article className="run-card">
      <header className="run-card-header">
        <div>
          <h3>{run.prompt}</h3>
          <p className="run-card-subtitle">
            {run.model} · {run.provider}
            {run.metadata.test_version && ` · Test v${run.metadata.test_version}`}
          </p>
        </div>
        <span className="status-badge" data-run-status={run.status}>
          {run.status}
        </span>
      </header>

      <section className="run-card-section">
        <h4>Response</h4>
        <pre className="run-response">{run.response}</pre>
      </section>

      <section className="run-card-section">
        <h4>Evaluation</h4>
        <p>
          Score: <strong data-passed={run.passed}>{run.score}</strong> (
          {run.passed ? "passed" : "failed"})
        </p>
        {run.criteria.length > 0 && (
          <ul className="evaluation-list">
            {run.criteria.map((criterion) => (
              <li key={criterion.name}>
                <span>{criterion.name}</span>
                <span data-passed={criterion.passed}>
                  {criterion.score} ({criterion.passed ? "passed" : "failed"}) — {criterion.detail}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="run-card-section">
        <h4>Run metrics</h4>
        <dl className="metrics-grid">
          <dt>Latency</dt>
          <dd>{run.latency_ms} ms</dd>
          {usage?.input_tokens !== undefined && (
            <>
              <dt>Input tokens</dt>
              <dd>{usage.input_tokens}</dd>
            </>
          )}
          {usage?.output_tokens !== undefined && (
            <>
              <dt>Output tokens</dt>
              <dd>{usage.output_tokens}</dd>
            </>
          )}
          <dt>Created</dt>
          <dd>{new Date(run.created_at).toLocaleString()}</dd>
        </dl>
      </section>
      {run.metadata.test_id && (
        <button type="button" className="use-test-button" onClick={() => onUseTest(run)}>
          Load this test into the form
        </button>
      )}
    </article>
  );
}

function RunResults({
  runs,
  loading,
  error,
  onRefresh,
  onUseTest,
}: {
  runs: RunResponse[];
  loading: boolean;
  error: string;
  onRefresh: () => void;
  onUseTest: (run: RunResponse) => void;
}) {
  return (
    <section className="run-results">
      <div className="run-results-header">
        <h2>Test run results</h2>
        <button type="button" onClick={onRefresh} disabled={loading}>
          {loading ? "Loading…" : "Refresh saved runs"}
        </button>
      </div>
      {error && <p className="error-text">Saved runs could not be loaded: {error}</p>}

      {loading && runs.length === 0 ? (
        <p className="muted">Loading saved runs…</p>
      ) : runs.length === 0 ? (
        <p className="muted">No saved runs yet — submit a prompt above to test a model.</p>
      ) : (
        <div className="run-card-list">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} onUseTest={onUseTest} />
          ))}
        </div>
      )}
    </section>
  );
}

export default RunResults;
