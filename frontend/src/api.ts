// API client for the FastAPI backend. The request/response shapes here follow
// the most complete confirmed backend contract across the team's branches
// (omar-db-history-integration-2): POST /runs executes and saves a run,
// GET /runs returns saved history. Both endpoints are strict about unknown
// fields (Pydantic `extra="forbid"`), so only send fields listed here.

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface RunCreateRequest {
  test_name: string;
  prompt: string;
  model: string;
  temperature: number;
  expected_keywords: string[];
  minimum_length: number;
  minimum_sentences: number;
  forbidden_terms: string[];
  test_id?: string;
  test_version?: number;
}

export interface CriterionResult {
  name: string;
  passed: boolean;
  score: number;
  detail: string;
}

export interface RunResponse {
  id: string;
  status: string;
  prompt: string;
  model: string;
  provider: string;
  response: string;
  score: number;
  passed: boolean;
  criteria: CriterionResult[];
  latency_ms: number;
  created_at: string;
  metadata: {
    requested_model: string;
    temperature: number;
    expected_keywords: string[];
    minimum_length: number;
    minimum_sentences: number;
    forbidden_terms: string[];
    usage: {
      input_tokens: number;
      output_tokens: number;
    };
    schema_version: string;
    test_id?: string;
    test_version?: number;
    test_name: string;
  };
}

async function responseError(response: Response): Promise<Error> {
  let detail = response.statusText;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      detail = String((body as { detail: unknown }).detail);
    }
  } catch {
    // Response body wasn't JSON; fall back to statusText.
  }
  return new Error(detail);
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

export async function listRuns(limit = 100, signal?: AbortSignal): Promise<RunResponse[]> {
  const response = await fetch(`${apiBaseUrl}/runs?limit=${limit}`, { signal });
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as RunResponse[];
}

export async function runEvaluation(
  request: RunCreateRequest,
  signal?: AbortSignal,
): Promise<RunResponse> {
  const response = await fetch(`${apiBaseUrl}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Run failed: ${(await responseError(response)).message}`);
  }

  return (await response.json()) as RunResponse;
}
