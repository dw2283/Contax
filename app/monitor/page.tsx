"use client";

import { Activity, Loader2, Network, Play, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentTopology } from "../components/monitor/AgentTopology";
import { GanttChart } from "../components/monitor/GanttChart";
import { MemoryPanel } from "../components/monitor/MemoryPanel";
import { fetchStatus, latestSpanByAgent, redisStatusLabel, runSampleIngest, StatusResponse } from "../lib/monitor";

const POLL_MS = 3000;

export default function MonitorPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedKind, setSelectedKind] = useState<"ingest" | "match" | null>(null);
  const [isSampling, setIsSampling] = useState(false);
  const userPicked = useRef(false);

  const load = useCallback(async () => {
    try {
      const next = await fetchStatus();
      setStatus(next);
      setError(null);
      if (!userPicked.current) {
        // Default to the most recently finished run.
        const runs = Object.values(next.runs);
        const latest = runs.sort((a, b) => (b.finished_at ?? 0) - (a.finished_at ?? 0))[0];
        if (latest) setSelectedKind(latest.kind as "ingest" | "match");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach /api/status");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const latest = useMemo(() => (status ? latestSpanByAgent(status.runs) : new Map()), [status]);
  const visionFanout = useMemo(
    () => status?.runs.ingest?.spans.filter((s) => s.agent === "vision_agent").length ?? 0,
    [status],
  );
  const availableRuns = useMemo(
    () => (status ? (["ingest", "match"] as const).filter((k) => status.runs[k]) : []),
    [status],
  );
  const selectedRun = status && selectedKind ? status.runs[selectedKind] : undefined;

  async function handleSample() {
    setIsSampling(true);
    try {
      await runSampleIngest();
      await load();
      setSelectedKind("ingest");
      userPicked.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sample ingest failed");
    } finally {
      setIsSampling(false);
    }
  }

  return (
    <main className="monitor-page">
      <header className="monitor-topbar">
        <div className="toolbar-brand">
          <span><Activity size={19} /></span>
          <div>
            <h1>Agent Monitor</h1>
            <p>
              {status ? `${status.redis.person_count} people · redis: ${redisStatusLabel(status.redis.status)}` : "connecting…"}
              {status ? ` · weave: ${status.weave_project}` : ""}
            </p>
          </div>
        </div>
        <nav className="app-nav">
          <Link href="/" className="nav-link"><Network size={15} /> Graph</Link>
          <span className="nav-link active"><Activity size={15} /> Monitor</span>
        </nav>
      </header>

      {error ? <p className="graph-error">{error} — is the FastAPI backend running on :8000?</p> : null}

      <section className="mon-grid">
        <div className="mon-panel mon-topo-panel">
          <h2 className="mon-panel-title"><Network size={15} /> Agent topology · data flow</h2>
          <div className="mon-topo">
            <AgentTopology latest={latest} visionFanout={visionFanout} />
          </div>
        </div>

        <MemoryPanel status={status ?? emptyStatus} latest={latest} />

        <div className="mon-panel mon-gantt-panel">
          <div className="mon-gantt-head">
            <h2 className="mon-panel-title"><RefreshCw size={15} /> Agent timeline · @weave.op durations</h2>
            <div className="mon-run-tabs">
              {availableRuns.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className={selectedKind === kind ? "active" : ""}
                  onClick={() => {
                    setSelectedKind(kind);
                    userPicked.current = true;
                  }}
                >
                  {status?.runs[kind]?.label ?? kind}
                </button>
              ))}
              <button type="button" className="mon-sample" onClick={() => void handleSample()} disabled={isSampling}>
                {isSampling ? <Loader2 className="spin" size={13} /> : <Play size={13} />}
                Run sample ingest
              </button>
            </div>
          </div>
          {selectedRun ? (
            <GanttChart run={selectedRun} />
          ) : (
            <p className="mon-empty">
              No runs recorded yet. Click <strong>Run sample ingest</strong>, or load demo people / run a match from the Graph tab.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}

const emptyStatus: StatusResponse = {
  weave_project: "",
  redis: { status: "connecting…", person_count: 0, vector_index_ready: false },
  embed: { count: 0, total_ms: 0 },
  runs: {},
};
