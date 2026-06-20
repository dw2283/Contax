import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";
import type { PRMNode } from "../lib/types";

export function TagNode({ data }: NodeProps<PRMNode>) {
  if (data.nodeKind !== "tag") return null;

  const updatedCount = data.updatedCount ?? 0;
  const style = {
    "--tag-accent": data.accent,
    "--tag-tint": data.tint,
    width: data.size,
    height: data.size,
  } as CSSProperties;

  return (
    <div
      className={`rg-tag-node ${data.kind} ${updatedCount ? "updated" : ""} ${data.highlighted ? "matched" : ""} ${data.selected ? "selected" : ""}`}
      style={style}
      title={`${data.categoryLabel}: ${data.label} · ${data.count} ${data.count === 1 ? "person" : "people"}`}
    >
      <Handle className="tag-center-handle" id="src" type="source" position={Position.Top} />
      <Handle className="tag-center-handle" id="tgt" type="target" position={Position.Top} />
      {updatedCount ? <span className="tag-updated-dot" title={`${updatedCount} updated contact${updatedCount === 1 ? "" : "s"}`} /> : null}
      <span className="tag-kind-dot" />
      <strong className="tag-label">{data.label}</strong>
      <span className="tag-count">{data.count}</span>
    </div>
  );
}

export function PersonNode({ data }: NodeProps<PRMNode>) {
  if (data.nodeKind !== "person") return null;

  return (
    <div
      className={`rg-person-node ${data.highlighted ? "highlighted" : ""} ${data.updated ? "updated" : ""} ${data.selected ? "selected" : ""}`}
      style={{ width: data.size, height: data.size } as CSSProperties}
      title={`${data.label} · ${data.subtitle}`}
    >
      <Handle className="tag-center-handle" id="src" type="source" position={Position.Top} />
      <Handle className="tag-center-handle" id="tgt" type="target" position={Position.Top} />
      <span className="rg-person-avatar">{data.label.slice(0, 1)}</span>
      <span className="rg-person-label">
        <strong>{data.label}</strong>
        <small>{data.sourceLabel}</small>
      </span>
    </div>
  );
}

export const graphNodeTypes = {
  person: PersonNode,
  tag: TagNode,
};
