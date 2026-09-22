export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Provisional endpoint path. Update VITE_RUNS_ENDPOINT (or the default below)
// once Pranjal's run-results API route is finalized.
const runsEndpointPath = import.meta.env.VITE_RUNS_ENDPOINT ?? "/runs";

export interface ModelResponse {
  content: string;
  rawResponseJson?: unknown;
}

export interface ObjectiveEvaluation {
  criterionId: string;
  criterionLabel?: string;
  score: number;
  maxScore?: number;
  passed: boolean;
}

export interface SubjectiveEvaluation {
  criterionId: string;
  criterionLabel?: string;
  evaluatorId: string;
  score: number;
  maxScore?: number;
  notes?: string;
}

export interface RunMetrics {
  status: string;
  startedAt?: string;
  completedAt?: string;
  latencyMs?: number;
  promptTokens?: number;
  completionTokens?: number;
  errorMessage?: string;
}

export interface TestRunResult {
  runId: string;
  testName?: string;
  modelName?: string;
  metrics: RunMetrics;
  response: ModelResponse | null;
  objectiveEvaluations: ObjectiveEvaluation[];
  subjectiveEvaluations: SubjectiveEvaluation[];
}

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch(`${apiBaseUrl}/health`, { signal });
  const body: unknown = await response.json();
  return (
    response.ok &&
    typeof body === "object" &&
    body !== null &&
    "status" in body &&
    body.status === "ok"
  );
}

export async function fetchRunResults(signal?: AbortSignal): Promise<TestRunResult[]> {
  const response = await fetch(`${apiBaseUrl}${runsEndpointPath}`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to fetch run results: ${response.status} ${response.statusText}`);
  }
  const body: unknown = await response.json();
  if (!Array.isArray(body)) {
    throw new Error("Unexpected run results response: expected an array");
  }
  return body as TestRunResult[];
}
