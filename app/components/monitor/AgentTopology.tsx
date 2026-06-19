import { useMemo } from "react";
import type { CSSProperties } from "react";
import { redactRedisEndpoints } from "../../lib/monitor";
import type { AgentSpan } from "../../lib/monitor";

type AgentData = {
  label: string;
  role: string;
  accent: string;
  fanout?: number;
  span?: AgentSpan;
};

type IoData = { label: string; kind: "in" | "out" };
type NodeBox = { left: number; top: number; width: number };

function boxStyle(box: NodeBox): CSSProperties {
  return { left: box.left, top: box.top, width: box.width };
}

function AgentCard({
  data,
  box,
  compact = false,
}: {
  data: AgentData;
  box: NodeBox;
  compact?: boolean;
}) {
  const span = data.span;
  const state = span ? (span.status === "error" ? "error" : "ran") : "idle";
  return (
    <div
      className={`topo-agent ${data.fanout ? "fanout" : ""} ${compact ? "compact" : ""}`}
      style={{ ...boxStyle(box), borderTopColor: data.accent }}
    >
      <div className="topo-agent-head">
        <span className={`topo-dot ${state}`} />
        <strong>{data.label}</strong>
        {data.fanout ? <em className="topo-fanout">×{data.fanout}</em> : null}
      </div>
      <p className="topo-role">{data.role}</p>
      {span ? (
        <p className="topo-metric">{span.duration_ms.toFixed(2)} ms · {redactRedisEndpoints(span.summary || span.status)}</p>
      ) : (
        <p className="topo-metric idle">idle</p>
      )}
    </div>
  );
}

function IoNode({ data, box }: { data: IoData; box: NodeBox }) {
  return (
    <div className={`topo-io ${data.kind}`} style={boxStyle(box)}>
      <span>{data.label}</span>
    </div>
  );
}

function FanoutCluster({
  data,
  box,
  count,
}: {
  data: AgentData;
  box: NodeBox;
  count: number;
}) {
  const visibleBranches = Math.max(3, Math.min(count || 3, 6));
  return (
    <div className="topo-fanout-cluster" style={{ ...boxStyle(box), borderTopColor: data.accent }}>
      <div className="topo-agent-head">
        <span className={`topo-dot ${data.span?.status === "error" ? "error" : data.span ? "ran" : "idle"}`} />
        <strong>{data.label}</strong>
        {count ? <em className="topo-fanout">×{count}</em> : null}
      </div>
      <p className="topo-role">{data.role}</p>
      <div className="topo-branches" aria-label={`${visibleBranches} vision branches`}>
        {Array.from({ length: visibleBranches }).map((_, index) => (
          <span key={index}>shot {index + 1}</span>
        ))}
      </div>
      {data.span ? (
        <p className="topo-metric">{data.span.duration_ms.toFixed(2)} ms · {redactRedisEndpoints(data.span.summary || data.span.status)}</p>
      ) : (
        <p className="topo-metric idle">idle</p>
      )}
    </div>
  );
}

function MemoryNode({ box }: { box: NodeBox }) {
  return (
    <div className="topo-memory-node" style={boxStyle(box)}>
      <strong>Redis memory</strong>
      <span>people + vectors</span>
    </div>
  );
}

export function AgentTopology({
  latest,
  visionFanout,
}: {
  latest: Map<string, AgentSpan>;
  visionFanout: number;
}) {
  const data = useMemo(() => {
    const agent = (id: string, label: string, role: string, accent: string, fanout?: number): AgentData => ({
      label,
      role,
      accent,
      fanout,
      span: latest.get(id),
    });
    return {
      orchestrator: agent("orchestrator", "orchestrator", "LangGraph fan-out", "#5b86df"),
      vision: agent("vision_agent", "vision_agent", "parallel screenshot extraction", "#8b6fd6", visionFanout || undefined),
      entity: agent("entity_resolution", "entity_resolution", "dedupe + merge", "#1f8a70"),
      embed: agent("embed_text", "embed_text", "vectorize profile text", "#d98c2b"),
      store: agent("redis_store", "redis_store", "RedisJSON + KNN", "#b1543d"),
      vector: agent("vector_search", "vector_search", "KNN recall", "#2f8f6b"),
      matchmaker: agent("matchmaker_agent", "matchmaker_agent", "rank + explain", "#2e6fca"),
    };
  }, [latest, visionFanout]);

  return (
    <div className="topo-dag-scroll">
      <div className="topo-dag-canvas" aria-label="Agent topology DAG">
        <svg className="topo-wires" viewBox="0 0 1040 420" aria-hidden="true">
          <defs>
            <marker id="topo-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
          </defs>

          <path className="topo-wire" d="M136 112 H170" />
          <text className="topo-wire-label" x="142" y="101">image[]</text>

          <path className="topo-wire" d="M310 112 H336" />
          <path className="topo-wire" d="M336 112 V58 H350" />
          <path className="topo-wire" d="M336 112 H350" />
          <path className="topo-wire" d="M336 112 V166 H350" />
          <text className="topo-wire-label" x="314" y="101">fan-out</text>

          <path className="topo-wire" d="M520 58 H545 V112 H570" />
          <path className="topo-wire" d="M520 112 H570" />
          <path className="topo-wire" d="M520 166 H545 V112" />
          <text className="topo-wire-label" x="525" y="101">merge</text>

          <path className="topo-wire" d="M715 112 H755" />
          <text className="topo-wire-label" x="720" y="101">deduped</text>

          <path className="topo-wire" d="M885 112 H910" />
          <text className="topo-wire-label" x="872" y="101">vectors</text>

          <path className="topo-wire dashed" d="M972 175 C972 242 450 240 422 296" />
          <text className="topo-wire-label" x="602" y="249">KNN recall</text>

          <path className="topo-wire" d="M282 326 H350" />
          <text className="topo-wire-label" x="306" y="315">query</text>

          <path className="topo-wire" d="M495 326 H570" />
          <text className="topo-wire-label" x="505" y="315">candidates</text>

          <path className="topo-wire" d="M715 326 H755" />
          <text className="topo-wire-label" x="724" y="315">top-k</text>
        </svg>

        <span className="topo-section-label ingest">Ingest graph</span>
        <span className="topo-section-label match">Match graph</span>

        <IoNode data={{ label: "Screenshots", kind: "in" }} box={{ left: 24, top: 82, width: 112 }} />
        <AgentCard data={data.orchestrator} box={{ left: 170, top: 76, width: 140 }} />
        <FanoutCluster data={data.vision} box={{ left: 350, top: 26, width: 170 }} count={visionFanout} />
        <AgentCard data={data.entity} box={{ left: 570, top: 76, width: 145 }} />
        <AgentCard data={data.embed} box={{ left: 755, top: 76, width: 130 }} compact />
        <AgentCard data={data.store} box={{ left: 910, top: 76, width: 124 }} compact />

        <MemoryNode box={{ left: 910, top: 178, width: 124 }} />

        <IoNode data={{ label: "NL query", kind: "in" }} box={{ left: 170, top: 296, width: 112 }} />
        <AgentCard data={data.vector} box={{ left: 350, top: 290, width: 145 }} />
        <AgentCard data={data.matchmaker} box={{ left: 570, top: 290, width: 145 }} />
        <IoNode data={{ label: "Recommendations", kind: "out" }} box={{ left: 755, top: 296, width: 130 }} />
      </div>
    </div>
  );
}
