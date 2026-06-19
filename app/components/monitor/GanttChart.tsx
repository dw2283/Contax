import { ExternalLink } from "lucide-react";
import { redactRedisEndpoints } from "../../lib/monitor";
import type { MonitorRun } from "../../lib/monitor";

const COLORS: Record<string, string> = {
  orchestrator: "#94a7bd",
  vision_agent: "#8b6fd6",
  entity_resolution: "#1f8a70",
  embed_text: "#d98c2b",
  generate_demo: "#5b86df",
  redis_store: "#b1543d",
  vector_search: "#2f8f6b",
  matchmaker_agent: "#2e6fca",
};

const LABEL_W = 196;
const PLOT_X0 = LABEL_W + 10;
const SVG_W = 1060;
const PLOT_X1 = SVG_W - 32;
const PLOT_W = PLOT_X1 - PLOT_X0;
const ROW_H = 34;
const HEADER_H = 34;

function basename(group: string | null): string {
  if (!group) return "";
  return group.split("/").pop() ?? group;
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 3)}...` : value;
}

export function GanttChart({ run }: { run: MonitorRun }) {
  const spans = [...run.spans].sort((a, b) => a.start - b.start);
  if (!spans.length) {
    return <p className="mon-empty">This run recorded no agent spans.</p>;
  }

  const t0 = Math.min(...spans.map((s) => s.start), run.started_at);
  const t1 = Math.max(...spans.map((s) => s.end), run.finished_at ?? t0);
  const span = Math.max(t1 - t0, 1e-4);
  const totalMs = span * 1000;
  const height = HEADER_H + spans.length * ROW_H + 10;

  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="gantt">
      <div className="gantt-scroll">
        <svg viewBox={`0 0 ${SVG_W} ${height}`} width="100%" preserveAspectRatio="xMinYMin meet" role="img">
          {ticks.map((t) => {
            const x = PLOT_X0 + t * PLOT_W;
            return (
              <g key={t}>
                <line x1={x} y1={HEADER_H - 7} x2={x} y2={height - 6} stroke="#dde6ef" strokeWidth={1} />
                <text x={x} y={18} textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"} className="gantt-axis">
                  {(t * totalMs).toFixed(t === 0 ? 0 : totalMs < 10 ? 2 : 1)}ms
                </text>
              </g>
            );
          })}

          {spans.map((s, i) => {
            const y = HEADER_H + i * ROW_H;
            const x = PLOT_X0 + ((s.start - t0) / span) * PLOT_W;
            const w = Math.max(5, ((s.end - s.start) / span) * PLOT_W);
            const color = s.status === "error" ? "#c4424f" : COLORS[s.agent] ?? "#7c8b99";
            const label = s.group ? `${s.agent} / ${basename(s.group)}` : s.agent;
            const duration = `${s.duration_ms.toFixed(2)}ms`;
            const durationX = w > 76 ? x + w - 8 : Math.min(x + w + 8, PLOT_X1 - 2);
            return (
              <g key={`${s.agent}-${s.start}-${i}`}>
                <text x={8} y={y + ROW_H / 2 + 4} className="gantt-label">
                  {truncate(label, 31)}
                  <title>{label}</title>
                </text>
                <rect x={PLOT_X0} y={y + 7} width={PLOT_W} height={ROW_H - 14} className="gantt-track" rx={5} />
                <rect x={x} y={y + 6} width={w} height={ROW_H - 12} rx={5} fill={color}>
                  <title>{`${label} - ${duration} (${s.status})\n${redactRedisEndpoints(s.summary)}`}</title>
                </rect>
                <text
                  x={durationX}
                  y={y + ROW_H / 2 + 4}
                  className={`gantt-dur ${w > 76 ? "inside" : ""}`}
                  textAnchor={w > 76 ? "end" : "start"}
                >
                  {duration}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="gantt-foot">
        <span className="gantt-total">total {totalMs.toFixed(2)} ms · {spans.length} spans</span>
        {run.weave_call_url ? (
          <a href={run.weave_call_url} target="_blank" rel="noreferrer" className="gantt-weave">
            View in Weave <ExternalLink size={13} />
          </a>
        ) : (
          <span className="gantt-weave disabled">Weave trace off (set WANDB_API_KEY or run wandb login)</span>
        )}
      </div>
    </div>
  );
}
