"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { ExplorePanel } from "./components/ExplorePanel";
import { GraphCanvas } from "./components/GraphCanvas";
import { Toolbar } from "./components/Toolbar";
import { fetchPeople, fileToDataUrl, guessSource, ingestScreenshots, matchPeople, seedDemoPeople } from "./lib/api";
import { matchedTagIds } from "./lib/graph";
import { fetchStatus, type MonitorRun } from "./lib/monitor";
import type { Person, Recommendation, UploadItem } from "./lib/types";

const DEMO_PEOPLE_SIZE = 100;

function latestTraceRun(runs: { ingest?: MonitorRun; match?: MonitorRun }): MonitorRun | undefined {
  return [runs.match, runs.ingest]
    .filter((run): run is MonitorRun => Boolean(run?.weave_call_url))
    .sort((a, b) => (b.finished_at ?? b.started_at) - (a.finished_at ?? a.started_at))[0];
}

function mergePeopleById(current: Person[], incoming: Person[]): Person[] {
  const merged = new Map(current.map((person) => [person.id, person]));
  incoming.forEach((person) => merged.set(person.id, person));
  return [...merged.values()];
}

export default function Page() {
  const [people, setPeople] = useState<Person[]>([]);
  const [screenshotPreviews, setScreenshotPreviews] = useState<Record<string, string>>({});
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [redisStatus, setRedisStatus] = useState("pending");
  const [ingestTrace, setIngestTrace] = useState<string | null>(null);
  const [matchTrace, setMatchTrace] = useState<string | null>(null);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didAutoLoad = useRef(false);

  // Load persisted people only; demo seeding stays explicit so real-contact mode does not repopulate demo data.
  useEffect(() => {
    if (didAutoLoad.current) return;
    didAutoLoad.current = true;
    void loadInitialPeople();
    void restoreLatestTrace();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tags carried by the top matches glow yellow on the graph.
  const highlightedTags = useMemo(
    () => matchedTagIds(recommendations.slice(0, 3).map((item) => item.person)),
    [recommendations],
  );

  // Keep private contact details behind explicit tool calls instead of streaming the full graph into copilot context.
  useCopilotReadable({
    description: "High-level state of the user's relationship graph",
    value: {
      people_count: people.length,
      redis_status: redisStatus,
      has_matches: recommendations.length > 0,
    },
  });

  useCopilotAction({
    name: "findPeople",
    description:
      "Find the most relevant people in the user's network for a given need, " +
      "highlight their tags on the graph in yellow, and draft intro messages.",
    parameters: [
      {
        name: "need",
        type: "string",
        description: "What the user needs help with / the kind of person they want to find",
        required: true,
      },
    ],
    handler: async ({ need }) => runMatch(need),
  });

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;

    setIsIngesting(true);
    setError(null);
    setRecommendations([]);
    setSelectedTagId(null);
    setSelectedPerson(null);
    setMatchTrace(null);
    try {
      const nextUploads: UploadItem[] = await Promise.all(
        files.map(async (file) => {
          const imageBase64 = await fileToDataUrl(file);
          return {
            id: `${file.name}-${file.lastModified}`,
            file_name: file.name,
            raw_screenshot_ref: `uploads/${file.name}`,
            source: guessSource(file.name),
            image_base64: imageBase64,
          };
        }),
      );
      setScreenshotPreviews((current) => ({
        ...current,
        ...Object.fromEntries(nextUploads.map((item) => [item.raw_screenshot_ref, item.image_base64])),
      }));
      const payload = await ingestScreenshots(nextUploads);
      setPeople((current) => mergePeopleById(current, payload.result.people));
      setRedisStatus(payload.result.storage.redis_status);
      setIngestTrace(payload.weave_call_url ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not ingest screenshots");
    } finally {
      setIsIngesting(false);
    }
  }

  async function loadInitialPeople() {
    setIsSeeding(true);
    setError(null);
    setRecommendations([]);
    setSelectedTagId(null);
    setSelectedPerson(null);
    try {
      const existing = await fetchPeople();
      setPeople(existing.people);
      setRedisStatus(existing.redis_status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load people");
    } finally {
      setIsSeeding(false);
    }
  }

  async function restoreLatestTrace() {
    try {
      const status = await fetchStatus();
      const run = latestTraceRun(status.runs);
      if (!run?.weave_call_url) return;
      if (run.kind === "match") {
        setMatchTrace(run.weave_call_url);
      } else {
        setIngestTrace(run.weave_call_url);
      }
    } catch {
      // The trace link is optional; keep the graph usable if the monitor endpoint is unavailable.
    }
  }

  async function handleSeedDemo() {
    setIsSeeding(true);
    setError(null);
    setRecommendations([]);
    setSelectedTagId(null);
    setSelectedPerson(null);
    try {
      const seeded = await seedDemoPeople(DEMO_PEOPLE_SIZE);
      setPeople((current) => mergePeopleById(current, seeded.people));
      setRedisStatus(seeded.storage.redis_status);
      setError(seeded.warning ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load demo people");
    } finally {
      setIsSeeding(false);
    }
  }

  /** Run the matchmaker; updates the graph and returns a summary for the copilot. */
  async function runMatch(need: string): Promise<string> {
    const cleanQuery = need.trim();
    if (cleanQuery.length < 2) return "Please describe who you are looking for.";
    setError(null);
    try {
      const payload = await matchPeople(cleanQuery);
      setPeople(payload.people);
      setRecommendations(payload.result.recommendations);
      setRedisStatus(payload.redis_status);
      setMatchTrace(payload.weave_call_url ?? null);
      // Surface the match drafts in the panel.
      setSelectedTagId(null);
      setSelectedPerson(null);
      const recs = payload.result.recommendations;
      if (!recs.length) return "No matching people found in the network yet. Try ingesting screenshots first.";
      return (
        "Highlighted the matching tags in yellow and drafted intros:\n" +
        recs
          .slice(0, 3)
          .map(
            (r, i) =>
              `${i + 1}. ${r.person.name} (${r.person.role || "?"} @ ${r.person.company || "?"}) — ${r.reason}`,
          )
          .join("\n")
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not run the matchmaker";
      setError(message);
      return message;
    }
  }

  function clearHighlights() {
    setRecommendations([]);
  }

  return (
    <main className="prm-one-page">
      <section className="graph-workspace">
        <Toolbar
          peopleCount={people.length}
          redisStatus={redisStatus}
          isIngesting={isIngesting}
          isSeeding={isSeeding}
          traceUrl={matchTrace ?? ingestTrace}
          onChooseFiles={handleFiles}
          onSeedDemo={handleSeedDemo}
          onClearHighlights={clearHighlights}
        />

        {error ? <p className="graph-error">{error}</p> : null}

        <GraphCanvas
          people={people}
          highlightedTags={highlightedTags}
          selectedTagId={selectedTagId}
          selectedPerson={selectedPerson}
          onSelectTag={(id) => {
            setSelectedTagId(id);
            setSelectedPerson(null);
          }}
          onSelectPerson={setSelectedPerson}
          onClearSelection={() => {
            setSelectedTagId(null);
            setSelectedPerson(null);
          }}
        >
          <ExplorePanel
            recommendations={recommendations}
            selectedPerson={selectedPerson}
            screenshotPreviews={screenshotPreviews}
            onSelectPerson={setSelectedPerson}
            onCloseSelection={() => {
              setSelectedTagId(null);
              setSelectedPerson(null);
            }}
            onClearMatches={clearHighlights}
          />
        </GraphCanvas>
      </section>

      <CopilotSidebar
        defaultOpen
        clickOutsideToClose={false}
        labels={{
          title: "Network Copilot",
          placeholder: "Ask about your network…",
          initial:
            'Tell me who you need. e.g. "Find someone in SF who knows GPU kernels" — I will highlight the matching tags on the graph and draft an intro.',
        }}
        instructions={
          "You help the user navigate their personal relationship graph, which is organized by VLM-derived tags across companies, topics, roles, places, and sources. " +
          "Whenever the user describes a need or asks who to talk to, call the findPeople action. " +
          "After it returns, summarize the top matches in a sentence or two and mention the intro drafts are ready to review."
        }
      />
    </main>
  );
}
