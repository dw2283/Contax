import { Background, Controls, ReactFlow } from "@xyflow/react";
import type { Viewport } from "@xyflow/react";
import { ChevronLeft, FileImage, Network, Search, Sparkles } from "lucide-react";
import { ReactNode, useMemo, useState } from "react";
import { buildTagGraph, parseTagId } from "../lib/graph";
import type { GraphLod, Person } from "../lib/types";
import { graphNodeTypes } from "./GraphNodes";

const fitViewOptions = { padding: 0.16, minZoom: 0.52, maxZoom: 1.5 };

const legendItems = [
  { label: "Company", color: "#10b981" },
  { label: "Topic", color: "#6366f1" },
  { label: "Role", color: "#8b5cf6" },
  { label: "Place", color: "#f59e0b" },
  { label: "Source", color: "#0ea5e9" },
];

function lodLevel(zoom: number): GraphLod {
  if (zoom < 0.72) return "overview";
  if (zoom <= 1.05) return "cluster";
  return "detail";
}

function lodLabel(lod: GraphLod): string {
  if (lod === "overview") return "Overview";
  if (lod === "detail") return "Detail";
  return "Cluster";
}

type GraphCanvasProps = {
  people: Person[];
  highlightedTags: Set<string>;
  selectedTagId: string | null;
  selectedPerson: Person | null;
  onSelectTag: (id: string) => void;
  onSelectPerson: (person: Person | null) => void;
  onClearSelection: () => void;
  children?: ReactNode;
};

export function GraphCanvas({
  people,
  highlightedTags,
  selectedTagId,
  selectedPerson,
  onSelectTag,
  onSelectPerson,
  onClearSelection,
  children,
}: GraphCanvasProps) {
  const [lod, setLod] = useState<GraphLod>("cluster");
  const focusTag = selectedTagId ? parseTagId(selectedTagId) : null;

  const base = useMemo(
    () =>
      buildTagGraph(people, {
        focusTagId: selectedTagId,
        highlightedTags,
        lod,
        selectedPersonId: selectedPerson?.id ?? null,
      }),
    [people, selectedTagId, highlightedTags, lod, selectedPerson],
  );
  const layoutKey = useMemo(
    () => `${selectedTagId ?? "global"}|${people.map((person) => person.id).sort().join("|")}`,
    [people, selectedTagId],
  );

  if (!people.length) {
    return (
      <section className="graph-stage">
        <div className="empty-graph">
          <FileImage size={38} />
          <p>Upload contacts or load the demo graph.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="graph-stage">
      {children}

      <div className="graph-legend">
        {legendItems.map((item) => (
          <span key={item.label}><i style={{ background: item.color }} /> {item.label}</span>
        ))}
        <span><i className="legend-match" /> Match</span>
        <span><i className="legend-updated" /> Updated</span>
      </div>

      <div className="graph-mode-bar">
        {focusTag ? (
          <>
            <button type="button" onClick={onClearSelection}>
              <ChevronLeft size={14} /> All Network
            </button>
            <span>/</span>
            <strong>{focusTag.label}</strong>
          </>
        ) : (
          <>
            <Network size={14} />
            <strong>All Network</strong>
          </>
        )}
        <em><Search size={13} /> {lodLabel(lod)}</em>
        <em><Sparkles size={13} /> {base.nodes.length} nodes</em>
      </div>

      <div className={`tag-flow lod-${lod} ${focusTag ? "focus-mode" : "global-mode"}`} style={{ height: "100%", width: "100%" }}>
        <ReactFlow
          key={layoutKey}
          nodes={base.nodes}
          edges={base.edges}
          nodeTypes={graphNodeTypes}
          fitView
          fitViewOptions={fitViewOptions}
          minZoom={0.5}
          maxZoom={1.9}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          panOnScroll
          onMove={(_, viewport: Viewport) => {
            const next = lodLevel(viewport.zoom);
            setLod((current) => (current === next ? current : next));
          }}
          onNodeClick={(_, node) => {
            const data = node.data;
            if (data.nodeKind === "person") {
              onSelectPerson(data.person);
            } else {
              onSelectPerson(null);
              onSelectTag(node.id);
            }
          }}
          onPaneClick={() => {
            if (focusTag) onSelectPerson(null);
            else onClearSelection();
          }}
        >
          <Background color="#e5e7eb" gap={32} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  );
}
