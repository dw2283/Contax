import type {
  DeleteDemoResponse,
  IngestResponse,
  MatchResponse,
  MockInterviewBriefResponse,
  MockInterviewVapiMode,
  MockInterviewVapiResponse,
  PeopleExportResponse,
  PeopleResponse,
  SeedResponse,
  Source,
  Person,
  UploadItem,
} from "./types";

// Default to a same-origin proxy so local browsers do not need to call the
// FastAPI port directly.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/backend";

// Leave undefined by default so the backend's .env decides.
// Set NEXT_PUBLIC_* only when you explicitly want the browser to override it.
const WEAVE_MODE = process.env.NEXT_PUBLIC_WEAVE_MODE;
const REDIS_MODE = process.env.NEXT_PUBLIC_REDIS_MODE;

function weaveModeBody(): { weave_mode?: string } {
  return WEAVE_MODE ? { weave_mode: WEAVE_MODE } : {};
}

function redisModeBody(): { redis_mode?: string } {
  return REDIS_MODE ? { redis_mode: REDIS_MODE } : {};
}

async function parseError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return response.statusText || `HTTP ${response.status}`;

  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.join(", ");
    return JSON.stringify(body);
  } catch {
    return text;
  }
}

/** Guess which platform a screenshot came from, by filename. */
export function guessSource(fileName: string): Source {
  const lower = fileName.toLowerCase();
  if (lower.includes("linkedin") || lower.startsWith("li_") || lower.includes("li-")) return "linkedin";
  if (lower.includes("whatsapp") || lower.startsWith("wa_") || lower.includes("wa-")) return "whatsapp";
  return "wechat";
}

export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** Run the ingest agent pipeline. With no uploads, the backend runs its demo set. */
export async function ingestScreenshots(uploads: UploadItem[]): Promise<IngestResponse> {
  const body =
    uploads.length > 0
      ? {
          demo: false,
          ...weaveModeBody(),
          ...redisModeBody(),
          screenshots: uploads.map(({ source, raw_screenshot_ref, image_base64 }) => ({
            source,
            raw_screenshot_ref,
            image_base64,
          })),
        }
      : { demo: true, ...weaveModeBody(), ...redisModeBody() };

  const response = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Load a deterministic graph-friendly demo set directly into Redis. */
export async function seedDemoPeople(size = 100): Promise<SeedResponse> {
  const response = await fetch(`${API_BASE}/api/seed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      size,
      ...redisModeBody(),
    }),
  });
  if (response.ok) return response.json();

  const seedError = await parseError(response);
  if (response.status !== 404) throw new Error(seedError);

  const legacyResponse = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      demo: true,
      ...weaveModeBody(),
      ...redisModeBody(),
    }),
  });
  if (!legacyResponse.ok) throw new Error(seedError);

  const legacyPayload = (await legacyResponse.json()) as IngestResponse;
  return {
    people: legacyPayload.result.people,
    storage: legacyPayload.result.storage,
    warning: `Loaded the legacy ${legacyPayload.result.people.length}-person demo because the backend has not picked up /api/seed yet. Restart FastAPI to load 100 demo people.`,
  };
}

/** Load the current relationship graph from the configured Redis database. */
export async function fetchPeople(): Promise<PeopleResponse> {
  const query = REDIS_MODE ? `?redis_mode=${encodeURIComponent(REDIS_MODE)}` : "";
  const response = await fetch(`${API_BASE}/api/prm/people${query}`);
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Export the current contact database as JSON before destructive cleanup. */
export async function exportPeople(): Promise<PeopleExportResponse> {
  const query = REDIS_MODE ? `?redis_mode=${encodeURIComponent(REDIS_MODE)}` : "";
  const response = await fetch(`${API_BASE}/api/prm/export${query}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Delete only contacts marked as demo data. Requires backend confirmation. */
export async function deleteDemoPeople(): Promise<DeleteDemoResponse> {
  const response = await fetch(`${API_BASE}/api/prm/delete-demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      confirm: true,
      ...redisModeBody(),
    }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Run the ingest pipeline against the repository's bundled anonymized screenshots. */
export async function ingestLocalScreenshots(): Promise<IngestResponse> {
  const response = await fetch(`${API_BASE}/api/ingest-local`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...weaveModeBody(),
      ...redisModeBody(),
    }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Run the matchmaker agent for a natural-language query. */
export async function matchPeople(query: string): Promise<MatchResponse> {
  const response = await fetch(`${API_BASE}/match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      ensure_demo_data: false,
      ...weaveModeBody(),
      ...redisModeBody(),
    }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Build a Vapi-ready mock interview brief for a selected contact. */
export async function prepareMockInterview(person: Person): Promise<MockInterviewBriefResponse> {
  const response = await fetch(`${API_BASE}/api/mock-interview/brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      person: {
        id: person.id,
        name: person.name,
        company: person.company,
        role: person.role,
        location: person.location,
        interests: person.interests,
        how_we_met: person.how_we_met,
        source: person.source,
      },
    }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/** Run a server-side Vapi validation against the prepared mock interview brief. */
export async function validateMockInterviewWithVapi(
  brief: MockInterviewBriefResponse,
  mode: MockInterviewVapiMode,
): Promise<MockInterviewVapiResponse> {
  const response = await fetch("/api/mock-interview/vapi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brief, mode }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}
