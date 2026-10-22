export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export interface ScoringWeights {
  keyword: number;
  relevance: number;
  length: number;
  sentences: number;
  forbidden: number;
  valid: number;
}
export const defaultWeights: ScoringWeights = {
  keyword: 30,
  relevance: 20,
  length: 15,
  sentences: 15,
  forbidden: 10,
  valid: 10,
};
export const scoringLabels: Record<keyof ScoringWeights, string> = {
  keyword: "Keyword coverage",
  relevance: "Prompt relevance",
  length: "Minimum length",
  sentences: "Sentence structure",
  forbidden: "Forbidden terms",
  valid: "Valid response",
};
export interface CriterionConfiguration {
  criterion_id: string;
  parameters: Record<string, unknown>;
  weight: number;
}
export interface CriterionDefinition {
  id: string;
  name: string;
  description: string;
  category: string;
  evaluator_type: string;
  parameter_schema: Record<string, unknown>;
  example_parameters: Record<string, unknown>;
}
export interface Suggestion {
  criterion_id: string;
  parameters: Record<string, unknown>;
  maximum_points: number;
  reason: string;
}
export interface Recommendation {
  recommendation_id: string;
  suggestions: Suggestion[];
  objective: string;
  test_prompt: string;
  provider: string;
  assistant_model: string;
  status: "generated";
  requires_approval: true;
}
export interface RunCreateRequest {
  test_name: string;
  prompt: string;
  model: string;
  temperature: number;
  base_system_prompt?: string | null;
  custom_system_prompt?: string | null;
  objective?: string;
  criteria?: CriterionConfiguration[];
  configuration_state?: "approved";
  recommendation_id?: string;
  weights?: ScoringWeights;
  expected_keywords?: string[];
  forbidden_terms?: string[];
  minimum_length?: number;
  minimum_sentences?: number;
  test_id?: string;
  test_version?: number;
}
export interface CriterionResult {
  name: string;
  criterion_id?: string | null;
  passed: boolean | null;
  score: number | null;
  detail: string;
  maximum_points?: number | null;
  normalized_score?: number | null;
  status?: string;
}
export interface RunResponse {
  id: string;
  status: string;
  prompt: string;
  model: string;
  provider: string;
  response: string;
  score: number | null;
  criteria: CriterionResult[];
  latency_ms: number;
  created_at: string;
  error?: { code: string; message: string } | null;
  metadata: {
    requested_model?: string;
    temperature?: number;
    expected_keywords?: string[];
    minimum_length?: number;
    minimum_sentences?: number;
    forbidden_terms?: string[];
    usage?: {
      input_tokens?: number | null;
      output_tokens?: number | null;
      total_tokens?: number | null;
    };
    base_system_prompt?: string | null;
    custom_system_prompt?: string | null;
    resolved_system_prompt?: string | null;
    objective?: string;
    criteria?: CriterionConfiguration[] | null;
    catalog_revision?: string;
    configuration_state?: string;
    recommendation_id?: string | null;
    generated_configuration?: Recommendation | null;
    schema_version: string;
    scoring_weights?: ScoringWeights | null;
    started_at?: string;
    test_id?: string;
    test_version?: number;
    test_name?: string;
  };
}
async function detail(
  response: Response,
): Promise<{ message: string; run_id?: string }> {
  try {
    const body = await response.json();
    const d = body.detail;
    if (typeof d === "string") return { message: d };
    if (Array.isArray(d))
      return {
        message: d
          .map((x) => `${x.loc?.slice(1).join(".") ?? "Input"}: ${x.msg}`)
          .join("; "),
      };
    if (d && typeof d === "object")
      return {
        message: String(d.message ?? "Request could not be completed"),
        run_id: d.run_id,
      };
  } catch {
    /* Preserve a useful message for non-JSON failures. */
  }
  return {
    message: `Request failed (${response.status}). Retry after checking the backend.`,
  };
}
async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { signal });
  if (!response.ok) throw new Error((await detail(response)).message);
  return response.json() as Promise<T>;
}
export function listRuns(signal?: AbortSignal) {
  return get<RunResponse[]>("/runs?limit=100", signal);
}
export function getRun(id: string, signal?: AbortSignal) {
  return get<RunResponse>(`/runs/${encodeURIComponent(id)}`, signal);
}
export async function checkHealth(signal?: AbortSignal) {
  return (await get<{ status: string }>("/health", signal)).status === "ok";
}
export function listCriteria(signal?: AbortSignal) {
  return get<{ catalog_revision: string; criteria: CriterionDefinition[] }>(
    "/evaluation/criteria",
    signal,
  );
}
export async function suggestCriteria(
  objective: string,
  test_prompt: string,
  signal?: AbortSignal,
): Promise<Recommendation> {
  const response = await fetch(`${apiBaseUrl}/assistant/suggest-criteria`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ objective, test_prompt }),
    signal,
  });
  if (!response.ok) throw new Error((await detail(response)).message);
  return response.json();
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
    const d = await detail(response);
    if (d.run_id) return getRun(d.run_id, signal);
    throw new Error(d.message);
  }
  return response.json();
}
