import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceRadial,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";
import type { SimulationLinkDatum, SimulationNodeDatum } from "d3-force";
import type { Edge } from "@xyflow/react";
import type { GraphLod, Person, PRMNode, Tag, TagKind } from "./types";
import { isUpdatedContactPerson } from "./realScreenshots";

const TAG_THEME: Record<TagKind, { accent: string; label: string; priority: number; tint: string }> = {
  company: { accent: "#10b981", label: "Company", priority: 2, tint: "#ecfdf5" },
  topic: { accent: "#6366f1", label: "Topic", priority: 1, tint: "#eef2ff" },
  role: { accent: "#8b5cf6", label: "Role", priority: 3, tint: "#f5f3ff" },
  location: { accent: "#f59e0b", label: "Place", priority: 4, tint: "#fffbeb" },
  source: { accent: "#0ea5e9", label: "Source", priority: 5, tint: "#f0f9ff" },
};

const SOURCE_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  wechat: "WeChat",
  whatsapp: "WhatsApp",
};

const LOD_LIMITS: Record<GraphLod, { minCount: number; maxTags: number; maxEdges: number }> = {
  overview: { minCount: 16, maxTags: 8, maxEdges: 14 },
  cluster: { minCount: 4, maxTags: 28, maxEdges: 72 },
  detail: { minCount: 1, maxTags: 90, maxEdges: 180 },
};

const LOD_KIND_CAPS: Record<GraphLod, Partial<Record<TagKind, number>>> = {
  overview: { topic: 5, location: 1, source: 2, role: 1, company: 0 },
  cluster: { topic: 13, company: 4, role: 4, location: 4, source: 3 },
  detail: {},
};

const FOCUS_LIMITS: Record<GraphLod, { people: number; relatedTags: number; personEdges: number }> = {
  overview: { people: 0, relatedTags: 10, personEdges: 0 },
  cluster: { people: 18, relatedTags: 14, personEdges: 16 },
  detail: { people: 60, relatedTags: 28, personEdges: 55 },
};

type BuildGraphOptions = {
  focusTagId?: string | null;
  highlightedTags?: Set<string>;
  highlightedPersonIds?: Set<string>;
  lod?: GraphLod;
  selectedPersonId?: string | null;
};

interface SimNode extends SimulationNodeDatum {
  id: string;
  nodeKind: "tag" | "person";
  kind?: TagKind;
  label: string;
  count: number;
  updatedCount: number;
  size: number;
  person?: Person;
  score: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  source: string | SimNode;
  target: string | SimNode;
  weight: number;
  relation: "cooccurrence" | "membership" | "shared_context";
}

type TagCountNode = {
  id: string;
  kind: TagKind;
  label: string;
  count: number;
  updatedCount: number;
  size: number;
  score: number;
};

export function tagId(kind: TagKind, label: string): string {
  return `${kind}:${label}`;
}

export function parseTagId(id: string): Tag | null {
  const index = id.indexOf(":");
  if (index < 1) return null;
  const kind = id.slice(0, index) as TagKind;
  if (!(kind in TAG_THEME)) return null;
  return { id, kind, label: id.slice(index + 1), count: 0 };
}

export function tagTheme(kind: TagKind) {
  return TAG_THEME[kind];
}

export function tagKindLabel(kind: TagKind): string {
  return TAG_THEME[kind].label;
}

/** Render a comma-joined source string ("wechat,linkedin") as "WeChat + LinkedIn". */
export function sourceLabel(source: string): string {
  return source
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => SOURCE_LABELS[item.toLowerCase()] ?? item)
    .join(" + ");
}

function cleanTagLabel(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function pushTag(tags: Tag[], kind: TagKind, label: string): void {
  const clean = cleanTagLabel(label);
  if (!clean) return;
  const normalizedLabel = kind === "source" ? SOURCE_LABELS[clean.toLowerCase()] ?? clean : clean;
  const id = tagId(kind, normalizedLabel);
  if (!tags.some((tag) => tag.id === id)) {
    tags.push({ id, kind, label: normalizedLabel, count: 0 });
  }
}

/** The unique VLM-derived tags carried by a person. */
export function tagsOfPerson(person: Person): Tag[] {
  const tags: Tag[] = [];
  pushTag(tags, "company", person.company);
  person.interests.slice(0, 5).forEach((interest) => pushTag(tags, "topic", interest));
  pushTag(tags, "role", person.role);
  pushTag(tags, "location", person.location);
  person.source
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((source) => pushTag(tags, "source", source));
  return tags;
}

/** Everyone who carries a given tag id. */
export function peopleForTag(people: Person[], id: string): Person[] {
  return people.filter((person) => tagsOfPerson(person).some((tag) => tag.id === id));
}

/** Tag ids touched by the current recommendations. */
export function matchedTagIds(people: Person[]): Set<string> {
  const ids = new Set<string>();
  people.forEach((person) => tagsOfPerson(person).forEach((tag) => ids.add(tag.id)));
  return ids;
}

function updatedAnchorTagId(tags: Tag[]): string | null {
  const company = tags.find((tag) => tag.kind === "company");
  return (company ?? tags[0])?.id ?? null;
}

function tagScore(kind: TagKind, count: number): number {
  return count * 10 - TAG_THEME[kind].priority;
}

function tagSize(count: number): number {
  return 58 + Math.min(30, Math.sqrt(count) * 5.2 + count * 0.9);
}

function personSize(updated = false): number {
  return updated ? 50 : 44;
}

function linkEndpointId(endpoint: string | SimNode): string {
  return typeof endpoint === "string" ? endpoint : endpoint.id;
}

function edgeWidth(weight: number): number {
  return Math.max(0.75, Math.min(5.2, 0.85 + Math.sqrt(weight) * 0.9));
}

function edgeOpacity(weight: number): number {
  return Math.min(0.82, 0.18 + Math.sqrt(weight) * 0.12);
}

function edgeClass(weight: number, relation: SimLink["relation"]): string {
  if (relation === "membership") return "tag-edge membership";
  if (weight >= 6) return "tag-edge strong";
  if (weight >= 3) return "tag-edge medium";
  return "tag-edge weak";
}

function toEdge(link: SimLink, index: number): Edge {
  const source = linkEndpointId(link.source);
  const target = linkEndpointId(link.target);
  return {
    id: `${link.relation}-${index}`,
    source,
    target,
    sourceHandle: "src",
    targetHandle: "tgt",
    type: "straight",
    className: edgeClass(link.weight, link.relation),
    style: {
      strokeWidth: edgeWidth(link.weight),
      strokeOpacity: edgeOpacity(link.weight),
    },
  };
}

function buildTagCounts(people: Person[]): Map<string, TagCountNode> {
  const tagMap = new Map<string, TagCountNode>();
  people.forEach((person) => {
    const tags = tagsOfPerson(person);
    const updatedAnchorId = isUpdatedContactPerson(person) ? updatedAnchorTagId(tags) : null;
    tags.forEach((tag) => {
      const contributesUpdatedBadge = tag.id === updatedAnchorId;
      const existing = tagMap.get(tag.id);
      if (existing) {
        existing.count += 1;
        existing.score = tagScore(existing.kind, existing.count);
        if (contributesUpdatedBadge) existing.updatedCount += 1;
      } else {
        tagMap.set(tag.id, {
          id: tag.id,
          kind: tag.kind,
          label: tag.label,
          count: 1,
          updatedCount: contributesUpdatedBadge ? 1 : 0,
          size: tagSize(1),
          score: tagScore(tag.kind, 1),
        });
      }
    });
  });
  tagMap.forEach((tag) => {
    tag.size = tagSize(tag.count);
    tag.score = tagScore(tag.kind, tag.count);
  });
  return tagMap;
}

function rankedTags(tags: TagCountNode[]): TagCountNode[] {
  return [...tags].sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (TAG_THEME[a.kind].priority !== TAG_THEME[b.kind].priority) {
      return TAG_THEME[a.kind].priority - TAG_THEME[b.kind].priority;
    }
    return a.label.localeCompare(b.label);
  });
}

function visibleTagIds(tags: TagCountNode[], lod: GraphLod): Set<string> {
  const limits = LOD_LIMITS[lod];
  const visible = new Set<string>();

  if (lod !== "overview") {
    const byKind = new Map<TagKind, TagCountNode[]>();
    tags.forEach((tag) => {
      const items = byKind.get(tag.kind) ?? [];
      items.push(tag);
      byKind.set(tag.kind, items);
    });
    byKind.forEach((items) => {
      const top = rankedTags(items)[0];
      if (top) visible.add(top.id);
    });
  }

  const caps = LOD_KIND_CAPS[lod];
  const perKindCount = new Map<TagKind, number>();
  rankedTags(tags).forEach((tag) => {
    if (visible.size >= limits.maxTags) return;
    if (tag.count < limits.minCount && lod !== "detail") return;
    const cap = caps[tag.kind];
    const current = perKindCount.get(tag.kind) ?? 0;
    if (cap !== undefined && current >= cap) return;
    visible.add(tag.id);
    perKindCount.set(tag.kind, current + 1);
  });

  return visible;
}

function pairLinksForPeople(people: Person[], visibleIds: Set<string>, maxEdges: number): SimLink[] {
  const pairCounts = new Map<string, number>();
  people.forEach((person) => {
    const ids = [...new Set(tagsOfPerson(person).map((tag) => tag.id))]
      .filter((id) => visibleIds.has(id))
      .sort();
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const key = `${ids[i]}|${ids[j]}`;
        pairCounts.set(key, (pairCounts.get(key) ?? 0) + 1);
      }
    }
  });

  return [...pairCounts.entries()]
    .map(([key, weight]) => {
      const [source, target] = key.split("|");
      return { source, target, weight, relation: "cooccurrence" as const };
    })
    .sort((a, b) => b.weight - a.weight)
    .slice(0, maxEdges);
}

function tagToSimNode(tag: TagCountNode): SimNode {
  return {
    id: tag.id,
    nodeKind: "tag",
    kind: tag.kind,
    label: tag.label,
    count: tag.count,
    updatedCount: tag.updatedCount,
    size: tag.size,
    score: tag.score,
  };
}

function simTagNodeToFlowNode(node: SimNode, highlightedTags: Set<string>, selected = false): PRMNode {
  const kind = node.kind ?? "topic";
  const theme = TAG_THEME[kind];
  return {
    id: node.id,
    type: "tag",
    position: { x: (node.x ?? 0) - node.size / 2, y: (node.y ?? 0) - node.size / 2 },
    data: {
      nodeKind: "tag",
      kind,
      label: node.label,
      categoryLabel: theme.label,
      count: node.count,
      updatedCount: node.updatedCount,
      size: node.size,
      accent: theme.accent,
      tint: theme.tint,
      highlighted: highlightedTags.has(node.id),
      selected,
    },
  };
}

function simPersonNodeToFlowNode(node: SimNode, selectedPersonId?: string | null, highlightedPersonIds?: Set<string>): PRMNode {
  const person = node.person!;
  return {
    id: node.id,
    type: "person",
    position: { x: (node.x ?? 0) - node.size / 2, y: (node.y ?? 0) - node.size / 2 },
    data: {
      nodeKind: "person",
      person,
      label: person.name,
      subtitle: [person.role, person.company].filter(Boolean).join(" @ ") || "Unknown contact",
      sourceLabel: sourceLabel(person.source),
      size: node.size,
      highlighted: highlightedPersonIds?.has(person.id) ?? false,
      selected: selectedPersonId === person.id,
      updated: isUpdatedContactPerson(person),
    },
  };
}

function runLayout(nodes: SimNode[], links: SimLink[], radial = false): void {
  const sim = forceSimulation<SimNode>(nodes)
    .force(
      "link",
      forceLink<SimNode, SimLink>(links)
        .id((d) => d.id)
        .distance((l) => (l.relation === "membership" ? 112 : 138 - Math.min(l.weight, 6) * 9))
        .strength((l) => (l.relation === "membership" ? 0.28 : Math.min(0.9, 0.18 + l.weight / 5))),
    )
    .force("charge", forceManyBody<SimNode>().strength((d) => (d.nodeKind === "person" ? -190 : -360)))
    .force("center", forceCenter(0, 0))
    .force("x", forceX<SimNode>(0).strength(0.035))
    .force("y", forceY<SimNode>(0).strength(0.035))
    .force("collide", forceCollide<SimNode>().radius((d) => d.size / 2 + (d.nodeKind === "person" ? 20 : 16)));

  if (radial) {
    sim.force("radial", forceRadial<SimNode>((d) => (d.id.startsWith("person:") ? 210 : d.score > 999 ? 0 : 118)).strength(0.16));
  }

  sim.stop().tick(radial ? 340 : 300);
}

function buildGlobalGraph(people: Person[], lod: GraphLod, highlightedTags: Set<string>): { nodes: PRMNode[]; edges: Edge[] } {
  const tagMap = buildTagCounts(people);
  const allTags = [...tagMap.values()];
  const visibleIds = visibleTagIds(allTags, lod);
  let simLinks = pairLinksForPeople(people, visibleIds, LOD_LIMITS[lod].maxEdges);
  const linkedIds = new Set<string>();
  simLinks.forEach((link) => {
    linkedIds.add(linkEndpointId(link.source));
    linkedIds.add(linkEndpointId(link.target));
  });
  const finalIds = lod === "overview" ? linkedIds : visibleIds;
  simLinks = simLinks.filter((link) => finalIds.has(linkEndpointId(link.source)) && finalIds.has(linkEndpointId(link.target)));
  const simNodes = rankedTags(allTags)
    .filter((tag) => finalIds.has(tag.id))
    .map(tagToSimNode);

  runLayout(simNodes, simLinks);

  return {
    nodes: simNodes.map((node) => simTagNodeToFlowNode(node, highlightedTags)),
    edges: simLinks.map(toEdge),
  };
}

function personRank(person: Person): number {
  return (
    person.interests.length * 4 +
    (person.company ? 3 : 0) +
    (person.role ? 2 : 0) +
    (isUpdatedContactPerson(person) ? 12 : 0)
  );
}

function relatedTagsForMembers(members: Person[], focusTagId: string): TagCountNode[] {
  const counts = new Map<string, TagCountNode>();
  members.forEach((person) => {
    tagsOfPerson(person).forEach((tag) => {
      if (tag.id === focusTagId) return;
      const existing = counts.get(tag.id);
      if (existing) {
        existing.count += 1;
        existing.score = tagScore(existing.kind, existing.count);
      } else {
        counts.set(tag.id, {
          id: tag.id,
          kind: tag.kind,
          label: tag.label,
          count: 1,
          updatedCount: 0,
          size: tagSize(1),
          score: tagScore(tag.kind, 1),
        });
      }
    });
  });
  counts.forEach((tag) => {
    tag.size = Math.max(38, tagSize(tag.count) - 4);
    tag.score = tagScore(tag.kind, tag.count);
  });
  return rankedTags([...counts.values()]);
}

function sharedContextWeight(a: Person, b: Person, focusTagId: string): number {
  const aTags = new Set(tagsOfPerson(a).map((tag) => tag.id).filter((id) => id !== focusTagId));
  const bTags = tagsOfPerson(b).map((tag) => tag.id).filter((id) => id !== focusTagId);
  let overlap = 0;
  bTags.forEach((id) => {
    if (aTags.has(id)) overlap += 1;
  });
  if (a.company && a.company === b.company) overlap += 2;
  if (a.location && a.location === b.location) overlap += 1;
  if (a.source && b.source && a.source === b.source) overlap += 1;
  return overlap;
}

function personLinks(people: Person[], focusTagId: string, maxEdges: number): SimLink[] {
  const links: SimLink[] = [];
  for (let i = 0; i < people.length; i += 1) {
    for (let j = i + 1; j < people.length; j += 1) {
      const weight = sharedContextWeight(people[i], people[j], focusTagId);
      if (weight >= 2) {
        links.push({
          source: `person:${people[i].id}`,
          target: `person:${people[j].id}`,
          weight,
          relation: "shared_context",
        });
      }
    }
  }
  return links.sort((a, b) => b.weight - a.weight).slice(0, maxEdges);
}

function buildFocusGraph(
  people: Person[],
  focusTagId: string,
  lod: GraphLod,
  highlightedTags: Set<string>,
  selectedPersonId?: string | null,
  highlightedPersonIds?: Set<string>,
): { nodes: PRMNode[]; edges: Edge[] } {
  const tagMap = buildTagCounts(people);
  const focusTag = tagMap.get(focusTagId);
  if (!focusTag) return buildGlobalGraph(people, lod, highlightedTags);

  const limits = FOCUS_LIMITS[lod];
  const members = peopleForTag(people, focusTagId).sort((a, b) => personRank(b) - personRank(a));
  const visiblePeople = members.slice(0, limits.people);
  const relatedTags = relatedTagsForMembers(members, focusTagId).slice(0, limits.relatedTags);
  const relatedTagRank = new Map(relatedTags.map((tag, index) => [tag.id, index]));

  const simNodes: SimNode[] = [
    { ...tagToSimNode({ ...focusTag, size: Math.max(68, focusTag.size + 8), score: 1000 }), fx: 0, fy: 0 },
    ...relatedTags.map(tagToSimNode),
    ...visiblePeople.map((person) => ({
      id: `person:${person.id}`,
      nodeKind: "person" as const,
      label: person.name,
      count: 1,
      updatedCount: 0,
      size: personSize(highlightedPersonIds?.has(person.id) || isUpdatedContactPerson(person)),
      person,
      score: personRank(person),
    })),
  ];

  const visibleRelated = new Set(relatedTags.map((tag) => tag.id));
  const simLinks: SimLink[] = [];
  visiblePeople.forEach((person) => {
    simLinks.push({
      source: focusTagId,
      target: `person:${person.id}`,
      weight: 2.6,
      relation: "membership",
    });
    tagsOfPerson(person)
      .filter((tag) => visibleRelated.has(tag.id))
      .sort((a, b) => (relatedTagRank.get(a.id) ?? 999) - (relatedTagRank.get(b.id) ?? 999))
      .slice(0, lod === "detail" ? 3 : 2)
      .forEach((tag) => {
        simLinks.push({
          source: `person:${person.id}`,
          target: tag.id,
          weight: 1.2,
          relation: "membership",
        });
      });
  });

  if (lod !== "overview") {
    simLinks.push(...personLinks(visiblePeople, focusTagId, limits.personEdges));
  }

  if (lod === "overview") {
    relatedTags.forEach((tag) => {
      simLinks.push({
        source: focusTagId,
        target: tag.id,
        weight: tag.count,
        relation: "cooccurrence",
      });
    });
  }

  runLayout(simNodes, simLinks, true);

  return {
    nodes: simNodes.map((node) =>
      node.nodeKind === "person"
        ? simPersonNodeToFlowNode(node, selectedPersonId, highlightedPersonIds)
        : simTagNodeToFlowNode(node, highlightedTags, node.id === focusTagId),
    ),
    edges: simLinks.map(toEdge),
  };
}

export function buildTagGraph(people: Person[], options: BuildGraphOptions = {}): { nodes: PRMNode[]; edges: Edge[] } {
  const lod = options.lod ?? "cluster";
  const highlightedTags = options.highlightedTags ?? new Set<string>();
  const highlightedPersonIds = options.highlightedPersonIds ?? new Set<string>();
  if (options.focusTagId) {
    return buildFocusGraph(people, options.focusTagId, lod, highlightedTags, options.selectedPersonId, highlightedPersonIds);
  }
  return buildGlobalGraph(people, lod, highlightedTags);
}

export { TAG_THEME };
