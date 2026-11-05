import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { addReview, listReviews } from "./api";
import type { HumanReview } from "./api";

const REVIEWER_KEY = "harness.reviewerId";
const rememberedReviewer = () => {
  try {
    return localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
};
const rememberReviewer = (value: string) => {
  try {
    localStorage.setItem(REVIEWER_KEY, value);
  } catch {
    /* Storage can be unavailable (private mode); the form still works. */
  }
};

export default function HumanReviews({ runId }: { runId: string }) {
  const [reviews, setReviews] = useState<HumanReview[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [reviewer, setReviewer] = useState(rememberedReviewer);
  const [rating, setRating] = useState("");
  const [rationale, setRationale] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    listReviews(runId, controller.signal)
      .then((result) => {
        setReviews(result);
        setLoadError("");
        setStatus("ready");
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        setLoadError(e instanceof Error ? e.message : "Reviews could not be loaded");
        setStatus("error");
      });
    return () => controller.abort();
  }, [runId, reload]);

  const ratingNumber = Number(rating);
  const problems = {
    reviewer: !reviewer.trim() ? "Enter your reviewer ID." : "",
    rating:
      !/^\d{1,3}$/.test(rating.trim()) || ratingNumber < 0 || ratingNumber > 100
        ? "Enter a whole number from 0 to 100."
        : "",
    rationale: !rationale.trim()
      ? "Explain the rating so others can see why."
      : rationale.length > 4000
        ? "Keep the explanation under 4,000 characters."
        : "",
  };
  const valid = !problems.reviewer && !problems.rating && !problems.rationale;
  const show = (field: keyof typeof problems) => touched[field] && problems[field];
  const touch = (field: string) => setTouched((t) => ({ ...t, [field]: true }));

  // The latest revision per reviewer is their current opinion; earlier ones stay as history.
  const latest = new Map<string, number>();
  for (const r of reviews)
    latest.set(r.reviewer_id, Math.max(latest.get(r.reviewer_id) ?? 0, r.revision));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched({ reviewer: true, rating: true, rationale: true });
    if (!valid || submitting) return;
    setSubmitting(true);
    setSubmitError("");
    setSaved("");
    try {
      const created = await addReview(runId, {
        reviewer_id: reviewer.trim(),
        rating: ratingNumber,
        rationale: rationale.trim(),
      });
      rememberReviewer(reviewer.trim());
      setReviews((previous) => [...previous, created]);
      setStatus("ready");
      setSaved(`Review saved as revision ${created.revision} for ${created.reviewer_id}.`);
      setRating("");
      setRationale("");
      setTouched({});
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "The review could not be saved");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel human-reviews" aria-labelledby="human-reviews-title">
      <h2 id="human-reviews-title">Human reviews</h2>
      <p className="muted">
        Separate from the automated score. A review never changes the automated total.
      </p>

      {status === "loading" && <p role="status">Loading reviews…</p>}
      {status === "error" && (
        <p role="alert" className="error-text">
          {loadError}{" "}
          <button type="button" className="text-button" onClick={() => setReload((x) => x + 1)}>
            Retry
          </button>
        </p>
      )}
      {status === "ready" && reviews.length === 0 && (
        <p className="muted">No human reviews yet for this run.</p>
      )}
      {reviews.length > 0 && (
        <ol className="review-list" aria-label="Human reviews, oldest first">
          {reviews.map((r) => {
            const current = latest.get(r.reviewer_id) === r.revision;
            return (
              <li key={r.id} className={`review-card ${current ? "" : "replaced"}`}>
                <div className="review-heading">
                  <strong>{r.reviewer_id}</strong>
                  <span className="review-rating">{r.rating} / 100</span>
                </div>
                <p className="muted review-meta">
                  Revision {r.revision} · {new Date(r.created_at).toLocaleString()} ·{" "}
                  <span className="review-state">{current ? "Current" : "Replaced"}</span>
                </p>
                <p className="review-rationale">{r.rationale}</p>
              </li>
            );
          })}
        </ol>
      )}

      <form className="review-form" onSubmit={(e) => void submit(e)} aria-busy={submitting} noValidate>
        <h3>Add a review</h3>
        <p className="muted">
          Using a reviewer ID that already reviewed this run saves a new revision. Earlier revisions
          are kept.
        </p>
        <div className="field-row">
          <label className="field">
            <span>Reviewer ID</span>
            <input
              value={reviewer}
              maxLength={128}
              aria-invalid={show("reviewer") ? true : undefined}
              aria-describedby={show("reviewer") ? "review-reviewer-error" : undefined}
              onChange={(e) => setReviewer(e.target.value)}
              onBlur={() => touch("reviewer")}
            />
            {show("reviewer") && (
              <span id="review-reviewer-error" className="error-text" role="alert">
                {problems.reviewer}
              </span>
            )}
          </label>
          <label className="field">
            <span>Rating (0–100)</span>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={100}
              step={1}
              value={rating}
              aria-invalid={show("rating") ? true : undefined}
              aria-describedby={show("rating") ? "review-rating-error" : undefined}
              onChange={(e) => setRating(e.target.value)}
              onBlur={() => touch("rating")}
            />
            {show("rating") && (
              <span id="review-rating-error" className="error-text" role="alert">
                {problems.rating}
              </span>
            )}
          </label>
        </div>
        <label className="field">
          <span>Rationale</span>
          <textarea
            rows={3}
            maxLength={4000}
            value={rationale}
            aria-invalid={show("rationale") ? true : undefined}
            aria-describedby={show("rationale") ? "review-rationale-error" : undefined}
            onChange={(e) => setRationale(e.target.value)}
            onBlur={() => touch("rationale")}
          />
          {show("rationale") && (
            <span id="review-rationale-error" className="error-text" role="alert">
              {problems.rationale}
            </span>
          )}
        </label>
        {submitError && (
          <p className="error-text" role="alert">
            {submitError}
          </p>
        )}
        {saved && <p role="status">{saved}</p>}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "Saving review…" : "Save review"}
        </button>
      </form>
    </section>
  );
}
