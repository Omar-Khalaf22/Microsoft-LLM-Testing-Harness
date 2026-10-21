// Shared contract for the FastAPI run and history endpoints.

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ScoringWeights {
  keyword: number;
  relevance: number;
  length: number;
  sentences: number;
  forbidden: number;
  valid: number;
}
export const defaultWeights: ScoringWeights = {
  keyword: 30, relevance: 20, length: 15, sentences: 15, forbidden: 10, valid: 10,
};
export const scoringLabels: Record<keyof ScoringWeights, string> = {
  keyword: "Keyword coverage", relevance: "Prompt relevance", length: "Minimum length",
  sentences: "Sentence structure", forbidden: "Forbidden terms", valid: "Valid response",
};

// One approved evaluation criterion, as described in the Prototype 2 proposal:
// {"id": "required_keywords", "parameters": {"keywords": ["PMOS", "NMOS"]}, "weight": 40}
export interface ApprovedCriterion {
  id: string;
  parameters: Record<string, unknown>;
  weight: number;
}

export interface RunCreateRequest {
  test_name: string;
  prompt: string;
  model: string;
  temperature: number;
  // Standard six-criterion scoring. Omitted when `criteria` is sent instead.
  weights?: ScoringWeights;
  expected_keywords?: string[];
  minimum_length?: number;
  minimum_sentences?: number;
  forbidden_terms?: string[];
  // Approved assistant criteria. Not accepted by the backend until the criteria dispatcher lands.
  criteria?: ApprovedCriterion[];
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
    scoring_weights?: ScoringWeights;
    started_at?: string;
    test_id?: string;
    test_version?: number;
    test_name: string;
  };
}

function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc: [...], msg: "..." }, ...]
    const messages = detail.map((item) => {
      if (typeof item === "object" && item !== null && "msg" in item) {
        const { msg, loc } = item as { msg: unknown; loc?: unknown };
        const where = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
        return where ? `${where}: ${String(msg)}` : String(msg);
      }
      return String(item);
    });
    return messages.join("; ") || fallback;
  }
  return fallback;
}

async function responseError(response: Response): Promise<Error> {
  let detail = response.statusText;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      detail = describeDetail((body as { detail: unknown }).detail, response.statusText);
    }
  } catch {
    // Response body wasn't JSON; fall back to statusText.
  }
  return new Error(detail);
}

export async function listRuns(signal?: AbortSignal): Promise<RunResponse[]> {
  const response = await fetch(`${apiBaseUrl}/runs?limit=100`, { signal });
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as RunResponse[];
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

// ---------------------------------------------------------------------------------------------
// LLM-assisted criteria recommendations (POST /assistant/suggest-criteria)
// ---------------------------------------------------------------------------------------------
//
// Contract from the Prototype 2 proposal: the request carries the testing objective and the test
// prompt (plus optional context); each suggestion carries a criterion ID, its parameters, a
// suggested weight, and a short reason. The response envelope is not final, so both a bare array
// and `{ "suggestions": [...] }` are accepted. Until the backend stabilizes the default mode is
// "mock"; set VITE_ASSISTANT_MODE=api to call the real endpoint.

export const assistantMode: "mock" | "api" =
  import.meta.env.VITE_ASSISTANT_MODE === "api" ? "api" : "mock";

export interface SuggestCriteriaRequest {
  objective: string;
  test_prompt: string;
  context?: string;
}

export interface CriterionSuggestion {
  criterion_id: string;
  parameters: Record<string, unknown>;
  weight: number;
  reason: string;
}

export interface SuggestionResult {
  suggestions: CriterionSuggestion[];
  /** How many returned items were malformed and therefore dropped. */
  invalid: number;
}

const MAX_SUGGESTIONS = 30;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Validate an untrusted assistant response. Malformed items are dropped and counted. */
export function normalizeSuggestions(raw: unknown): SuggestionResult {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.suggestions)
      ? raw.suggestions
      : null;
  if (items === null) {
    throw new Error("The assistant returned a response in an unexpected format.");
  }

  const suggestions: CriterionSuggestion[] = [];
  let invalid = 0;
  for (const item of items.slice(0, MAX_SUGGESTIONS)) {
    if (
      isRecord(item) &&
      typeof item.criterion_id === "string" &&
      item.criterion_id.trim() !== "" &&
      isRecord(item.parameters) &&
      typeof item.weight === "number" &&
      Number.isFinite(item.weight) &&
      item.weight >= 0 &&
      item.weight <= 100
    ) {
      suggestions.push({
        criterion_id: item.criterion_id.trim(),
        parameters: { ...item.parameters },
        weight: item.weight,
        reason: typeof item.reason === "string" ? item.reason.trim() : "",
      });
    } else {
      invalid += 1;
    }
  }
  invalid += Math.max(0, items.length - MAX_SUGGESTIONS);
  return { suggestions, invalid };
}

/** Scale weights to total exactly 100 (two decimals), keeping their proportions. */
export function balanceWeights(weights: number[]): number[] {
  if (weights.length === 0) return [];
  const safe = weights.map((weight) => (Number.isFinite(weight) && weight > 0 ? weight : 0));
  const sum = safe.reduce((total, weight) => total + weight, 0);
  const raw = sum > 0 ? safe.map((weight) => (weight / sum) * 10000) : safe.map(() => 10000 / safe.length);
  const floors = raw.map(Math.floor);
  let remainder = 10000 - floors.reduce((total, value) => total + value, 0);
  const order = raw
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index);
  for (let step = 0; remainder > 0 && step < order.length; step += 1, remainder -= 1) {
    floors[order[step].index] += 1;
  }
  return floors.map((value) => value / 100);
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

const MOCK_STOP_WORDS = new Set([
  "about", "answer", "should", "because", "include", "explain", "response", "model",
  "ensure", "check", "whether", "which", "their", "there", "would", "could", "write",
]);

function keywordCandidates(text: string): string[] {
  const quoted = Array.from(text.matchAll(/"([^"]{2,40})"/g), (match) => match[1].trim());
  const acronyms = text.match(/\b[A-Z][A-Z0-9]{1,}\b/g) ?? [];
  const explicit = Array.from(new Set([...quoted, ...acronyms])).slice(0, 5);
  if (explicit.length > 0) return explicit;
  const words = (text.toLowerCase().match(/[a-z][a-z-]{5,}/g) ?? []).filter(
    (word) => !MOCK_STOP_WORDS.has(word),
  );
  return Array.from(new Set(words)).slice(0, 3);
}

type MockSuggestion = Omit<CriterionSuggestion, "weight">;

const MOCK_RULES: { pattern: RegExp; build: (keywords: string[], text: string) => MockSuggestion[] }[] = [
  {
    pattern: /json/i,
    build: (keywords) => [
      {
        criterion_id: "valid_json",
        parameters: {},
        reason: "The objective calls for structured output, so the response should parse as JSON.",
      },
      {
        criterion_id: "json_required_keys",
        parameters: { keys: keywords.length > 0 ? keywords.slice(0, 3) : ["name"] },
        reason: "Structured output usually needs specific fields to be present.",
      },
    ],
  },
  {
    pattern: /e-?mail/i,
    build: () => [
      {
        criterion_id: "email_format",
        parameters: { mode: "contains" },
        reason: "The objective expects an email address to appear in the response.",
      },
    ],
  },
  {
    pattern: /\b(url|link|website|web page)\b/i,
    build: () => [
      {
        criterion_id: "url_format",
        parameters: { mode: "contains", schemes: ["http", "https"] },
        reason: "The objective expects a link, so a well-formed URL should be present.",
      },
    ],
  },
  {
    pattern: /\b(number|calculat\w*|compute\w*|how many|total|sum)\b/i,
    build: (_keywords, text) => [
      {
        criterion_id: "numeric_exact",
        parameters: { expected: Number(text.match(/-?\d+(?:\.\d+)?/)?.[0] ?? 0), marker: "Answer:" },
        reason: "A numeric answer is expected. Adjust the expected value to the correct result.",
      },
    ],
  },
  {
    pattern: /\b(brief|short|concise|at most|maximum|under|no more than)\b/i,
    build: () => [
      {
        criterion_id: "word_count_max",
        parameters: { maximum: 150 },
        reason: "The objective asks for a concise answer, so the length should be capped.",
      },
    ],
  },
  {
    pattern: /\b(detail\w*|thorough|comprehensive|in-depth|at least|minimum)\b/i,
    build: () => [
      {
        criterion_id: "word_count_min",
        parameters: { minimum: 80 },
        reason: "The objective asks for a thorough answer, so a minimum length is reasonable.",
      },
    ],
  },
  {
    pattern: /\b(section|heading|structure[d]?|report|outline)\b/i,
    build: () => [
      {
        criterion_id: "required_sections",
        parameters: { sections: ["Summary", "Conclusion"] },
        reason: "The objective describes a structured document with named sections.",
      },
    ],
  },
  {
    pattern: /\b(avoid|without|never|do not|don't|must not|prohibit\w*|forbid\w*)\b/i,
    build: (keywords) =>
      keywords.length > 0
        ? [
            {
              criterion_id: "forbidden_keywords",
              parameters: { keywords },
              reason: "The objective names content the response should not contain.",
            },
          ]
        : [],
  },
  {
    pattern: /\b(mention\w*|include\w*|cover\w*|explain\w*|keyword\w*|term\w*|contain\w*|must|should)\b/i,
    build: (keywords) =>
      keywords.length > 0
        ? [
            {
              criterion_id: "required_keywords",
              parameters: { keywords },
              reason: "The objective names concepts the response is expected to cover.",
            },
          ]
        : [],
  },
];

const MOCK_BASE_WEIGHTS = [30, 25, 20, 15, 10, 5];

async function mockSuggestions(request: SuggestCriteriaRequest, signal?: AbortSignal): Promise<unknown> {
  await wait(700, signal);
  const text = `${request.objective}\n${request.test_prompt}`;

  // Developer switches that exercise the error and edge-case states without a backend.
  if (request.objective.includes("[mock:error]")) {
    throw new Error("Could not generate criteria: the assistant service is unavailable (mock).");
  }
  if (request.objective.includes("[mock:empty]")) return [];
  if (request.objective.includes("[mock:invalid]")) {
    return {
      suggestions: [
        { criterion_id: "required_keywords", parameters: { keywords: ["example"] }, weight: 60, reason: "Valid sample." },
        { criterion_id: "", parameters: {}, weight: 20, reason: "Missing identifier." },
        { criterion_id: "word_count_max", parameters: "not an object", weight: 20, reason: "Bad parameters." },
        { criterion_id: "minimum_sentences", parameters: { minimum: 2 }, weight: "lots", reason: "Bad weight." },
      ],
    };
  }

  const keywords = keywordCandidates(request.objective);
  const picked: MockSuggestion[] = [];
  for (const rule of MOCK_RULES) {
    if (rule.pattern.test(request.objective)) {
      for (const suggestion of rule.build(keywords, text)) {
        if (!picked.some((existing) => existing.criterion_id === suggestion.criterion_id)) {
          picked.push(suggestion);
        }
      }
    }
  }
  if (picked.length === 0) {
    if (keywords.length > 0) {
      picked.push({
        criterion_id: "required_keywords",
        parameters: { keywords },
        reason: "Key terms from the objective should appear in a relevant answer.",
      });
    }
    picked.push({
      criterion_id: "minimum_sentences",
      parameters: { minimum: 2 },
      reason: "A substantive answer should span more than a single sentence.",
    });
  }

  const chosen = picked.slice(0, MOCK_BASE_WEIGHTS.length);
  const weights = balanceWeights(MOCK_BASE_WEIGHTS.slice(0, chosen.length));
  return chosen.map((suggestion, index) => ({ ...suggestion, weight: weights[index] }));
}

async function fetchSuggestions(request: SuggestCriteriaRequest, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${apiBaseUrl}/assistant/suggest-criteria`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Could not generate criteria: ${(await responseError(response)).message}`);
  }
  return response.json();
}

export async function suggestCriteria(
  request: SuggestCriteriaRequest,
  signal?: AbortSignal,
): Promise<SuggestionResult> {
  const raw =
    assistantMode === "api"
      ? await fetchSuggestions(request, signal)
      : await mockSuggestions(request, signal);
  return normalizeSuggestions(raw);
}
