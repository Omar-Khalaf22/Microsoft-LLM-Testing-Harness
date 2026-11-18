import type { RunSummary, TestReference } from "./api";
import SavedTestTree from "./SavedTestTree";

function SavedRuns({
  runs,
  selectedRunId,
  open,
  loading,
  error,
  onToggle,
  onRefresh,
  onOpenRun,
  hasMore,
  onLoadMore,
  reloadKey,
  onOpenVersion,
  onHome,
}: {
  runs: RunSummary[];
  hasMore: boolean;
  onLoadMore: () => void;
  selectedRunId?: string;
  open: boolean;
  loading: boolean;
  error: string;
  onToggle: () => void;
  onRefresh: () => void;
  onOpenRun: (run: RunSummary) => void;
  reloadKey: number;
  onOpenVersion?: (version: TestReference) => Promise<void> | void;
  onHome: () => void;
}) {
  return (
    <aside className="history-sidebar" aria-label="Saved tests">
      <div className="sidebar-top">
        <button
          className="sidebar-toggle home-button"
          type="button"
          onClick={onHome}
          aria-label="Home"
          title="Home"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
            <path
              d="M3 11.5 12 4l9 7.5M5.5 10v9.5h4.5v-5.5h4v5.5h4.5V10"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
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
        {open && <span className="sidebar-brand">Run History</span>}
      </div>
      {open && (
        <div id="saved-run-list" className="sidebar-content">
          <div className="sidebar-heading">
            <div>
              <p className="eyebrow">Your workspace</p>
              <h2>Saved Tests</h2>
            </div>
            <button
              type="button"
              className="refresh-button"
              onClick={onRefresh}
              disabled={loading}
              aria-label="Refresh saved runs"
              title="Refresh Saved Tests and Runs"
            >
              ↻
            </button>
          </div>
          <p className="sidebar-hint">
            Suites contain tests, tests contain versions, and each version lists its runs, newest
            first. Select a run to open its result.
          </p>
          {error && (
            <p className="sidebar-error" role="alert">
              Could not load runs: {error}
            </p>
          )}
          <SavedTestTree
            runs={runs}
            selectedRunId={selectedRunId}
            hasMore={hasMore}
            reloadKey={reloadKey}
            onOpenRun={onOpenRun}
            onOpenVersion={onOpenVersion}
          />
          {hasMore && (
            <button type="button" className="secondary-button" disabled={loading} onClick={onLoadMore}>
              {loading ? "Loading…" : "Load More Runs"}
            </button>
          )}
        </div>
      )}
    </aside>
  );
}

export default SavedRuns;
