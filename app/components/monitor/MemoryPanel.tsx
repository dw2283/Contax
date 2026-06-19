import { Boxes, CircleCheck, CircleSlash, Cpu, Database } from "lucide-react";
import { redactRedisEndpoints, redisStatusLabel } from "../../lib/monitor";
import type { AgentSpan, StatusResponse } from "../../lib/monitor";

const AGENT_ORDER = [
  "orchestrator",
  "vision_agent",
  "entity_resolution",
  "embed_text",
  "generate_demo",
  "redis_store",
  "vector_search",
  "matchmaker_agent",
];

export function MemoryPanel({
  status,
  latest,
}: {
  status: StatusResponse;
  latest: Map<string, AgentSpan>;
}) {
  const indexed = status.redis.vector_index_ready;
  const ordered = [...latest.entries()].sort(
    (a, b) => AGENT_ORDER.indexOf(a[0]) - AGENT_ORDER.indexOf(b[0]),
  );

  return (
    <div className="mon-panel">
      <h2 className="mon-panel-title"><Database size={15} /> Redis memory</h2>

      <div className="mem-stats">
        <div className="mem-stat">
          <span>People stored</span>
          <strong>{status.redis.person_count}</strong>
        </div>
        <div className="mem-stat">
          <span>Embeddings</span>
          <strong>{status.embed.count}</strong>
          <small>{status.embed.total_ms.toFixed(1)} ms total</small>
        </div>
        <div className={`mem-stat badge ${indexed ? "on" : "off"}`}>
          <span>Vector index</span>
          <strong>{indexed ? <CircleCheck size={16} /> : <CircleSlash size={16} />} {indexed ? "ready" : "lazy"}</strong>
          <small>redis: {redisStatusLabel(status.redis.status)}</small>
        </div>
      </div>

      <h3 className="mon-subtitle"><Cpu size={13} /> Last agent outputs</h3>
      <div className="agent-outputs">
        {ordered.length ? (
          ordered.map(([agent, span]) => (
            <div className="agent-output" key={agent}>
              <span className={`topo-dot ${span.status === "error" ? "error" : "ran"}`} />
              <div className="agent-output-text">
                <strong>{agent}</strong>
                <small>{redactRedisEndpoints(span.summary || span.status)}</small>
              </div>
              <em>{span.duration_ms.toFixed(2)} ms</em>
            </div>
          ))
        ) : (
          <p className="mon-empty"><Boxes size={15} /> No agent runs yet — run an ingest or match.</p>
        )}
      </div>
    </div>
  );
}
