import type { KeyboardEvent } from "react";

import type { RunResponse } from "./api";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function SavedRuns({
  runs,
  selectedRunId,
  open,
  loading,
  error,
  onToggle,
  onRefresh,
  onOpenRun,
}: {
  runs: RunResponse[];
  selectedRunId?: string;
  open: boolean;
  loading: boolean;
  error: string;
  onToggle: () => void;
  onRefresh: () => void;
  onOpenRun: (run: RunResponse) => void;
}) {
  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, run: RunResponse) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpenRun(run);
    }
  }

  return (
    <aside className="history-sidebar" aria-label="Saved runs">
      <div className="sidebar-top">
        <button
          className="sidebar-toggle"
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={open ? "saved-run-list" : undefined}
          aria-label={open ? "Close saved runs" : "Open saved runs"}
          title={open ? "Close saved runs" : "Open saved runs"}
        >
          <span aria-hidden="true">☰</span>
        </button>
        {open && <span className="sidebar-brand">Run history</span>}
      </div>
      {open && (
        <div id="saved-run-list" className="sidebar-content">
          <div className="sidebar-heading">
            <div>
              <p className="eyebrow">Your workspace</p>
              <h2>Saved runs</h2>
            </div>
            <button
              type="button"
              className="refresh-button"
              onClick={onRefresh}
              disabled={loading}
              aria-label="Refresh saved runs"
              title="Refresh saved runs"
            >
              ↻
            </button>
          </div>
          <p className="sidebar-hint">Double-click to load a run. Press Enter on a selected item.</p>
          {error && <p className="sidebar-error" role="alert">Could not load runs: {error}</p>}
          {loading && runs.length === 0 ? (
            <p className="sidebar-empty">Loading saved runs…</p>
          ) : runs.length === 0 ? (
            <p className="sidebar-empty">Your saved runs will appear here after the first evaluation.</p>
          ) : (
            <ul className="saved-run-list">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    className="saved-run-item"
                    type="button"
                    aria-pressed={selectedRunId === run.id}
                    aria-label={`Load ${run.metadata.test_name || "Untitled test"}, run from ${formatDate(run.created_at)}`}
                    onDoubleClick={() => onOpenRun(run)}
                    onKeyDown={(event) => handleKeyDown(event, run)}
                  >
                    <span className="saved-run-name">{run.metadata.test_name || "Untitled test"}</span>
                    <span className="saved-run-details">
                      {formatDate(run.created_at)} · {run.score}/100
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  );
}

export default SavedRuns;
