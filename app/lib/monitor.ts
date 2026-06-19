import { API_BASE } from "./api";

export type SpanStatus = "ok" | "error";

export type AgentSpan = {
  agent: string;
  group: string | null;
  start: number; // epoch seconds
  end: number;
  duration_ms: number;
  status: SpanStatus;
  summary: string;
};

export type MonitorRun = {
  kind: string; // "ingest" | "match"
  started_at: number;
  finished_at: number | null;
  spans: AgentSpan[];
  meta: Record<string, unknown>;
  label?: string;
  weave_call_url?: string | null;
  weave_mode?: string;
};

export type StatusResponse = {
  weave_project: string;
  redis: { status: string; person_count: number; vector_index_ready: boolean };
  embed: { count: number; total_ms: number };
  runs: { ingest?: MonitorRun; match?: MonitorRun };
};

export async function fetchStatus(): Promise<StatusResponse> {
  const response = await fetch(`${API_BASE}/api/status`, { cache: "no-store" });
  if (!response.ok) throw new Error(`status ${response.status}`);
  return response.json();
}

export function redisStatusLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized.includes("error")) return "storage issue";
  if (normalized.includes("off")) return "offline";
  if (normalized.includes("fake") || normalized.includes("memory")) return "local demo";
  if (normalized.includes("pending") || normalized.includes("connecting")) return "connecting";
  if (normalized.includes("redis")) return "connected";
  return "available";
}

export function redactRedisEndpoints(value: string): string {
  return value
    .replace(/redis:redis:\/\/\S+/gi, "redis: connected")
    .replace(/redis:\/\/\S+/gi, "redis: connected");
}

/** Kick off a demo screenshot ingest so the monitor shows the vision fan-out. */
export async function runSampleIngest(): Promise<void> {
  const response = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ demo: true }),
  });
  if (!response.ok) throw new Error(`ingest ${response.status}`);
}

/** Latest span per agent across all runs — drives the topology + memory panel. */
export function latestSpanByAgent(runs: StatusResponse["runs"]): Map<string, AgentSpan> {
  const latest = new Map<string, AgentSpan>();
  for (const run of [runs.ingest, runs.match]) {
    if (!run) continue;
    for (const span of run.spans) {
      const existing = latest.get(span.agent);
      if (!existing || span.end > existing.end) latest.set(span.agent, span);
    }
  }
  return latest;
}
