import type Vapi from "@vapi-ai/web";
import { ArrowLeft, Building2, Check, Copy, Loader2, Mic, MicOff, PhoneOff, Sparkles, Tag as TagIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { prepareMockInterview, validateMockInterviewWithVapi } from "../lib/api";
import { sourceLabel } from "../lib/graph";
import { isUpdatedContactPerson, screenshotFileName, screenshotUrlForPerson } from "../lib/realScreenshots";
import type { MockInterviewBriefResponse, MockInterviewVapiResponse, Person, Recommendation } from "../lib/types";

type ExplorePanelProps = {
  recommendations: Recommendation[];
  selectedPerson: Person | null;
  screenshotPreviews: Record<string, string>;
  onSelectPerson: (person: Person | null) => void;
  onCloseSelection: () => void;
  onClearMatches: () => void;
};

type VoiceTurn = {
  role: "assistant" | "user";
  text: string;
};

type VoiceCallStatus = "idle" | "preparing" | "connecting" | "live" | "ending";

function describeVapiError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (!error || typeof error !== "object") return "Vapi voice call failed";

  const details = error as {
    message?: unknown;
    errorMsg?: unknown;
    error?: unknown;
    code?: unknown;
    reason?: unknown;
    details?: unknown;
  };
  if (typeof details.message === "string" && details.message.trim()) return details.message;
  if (typeof details.errorMsg === "string" && details.errorMsg.trim()) return details.errorMsg;
  if (typeof details.error === "string" && details.error.trim()) return details.error;
  if (typeof details.reason === "string" && details.reason.trim()) return details.reason;
  if (typeof details.details === "string" && details.details.trim()) return details.details;
  if (typeof details.code === "string" && details.code.trim()) return details.code;
  try {
    return JSON.stringify(error);
  } catch {
    return "Vapi voice call failed";
  }
}

function formatVoiceProgress(event: unknown): string | null {
  if (!event || typeof event !== "object") return null;
  const payload = event as { stage?: unknown; status?: unknown };
  if (typeof payload.stage !== "string") return null;

  const stage = payload.stage.replaceAll("-", " ");
  const status = typeof payload.status === "string" ? payload.status.replaceAll("-", " ") : "working";
  return `${stage} · ${status}`;
}

async function ensureMicrophoneAccess() {
  if (typeof window === "undefined") {
    throw new Error("Voice calls must be started from a browser.");
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This browser does not expose microphone access. Try Chrome or Safari.");
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    const domError = error as { name?: string; message?: string };
    if (domError?.name === "NotAllowedError") {
      throw new Error("Microphone permission was denied. Allow microphone access for this site and try again.");
    }
    if (domError?.name === "NotFoundError") {
      throw new Error("No microphone was found on this device.");
    }
    if (domError?.name === "NotReadableError") {
      throw new Error("The microphone is busy or unavailable to the browser.");
    }
    if (domError?.message) {
      throw new Error(domError.message);
    }
    throw new Error("Could not access the microphone.");
  }
}

function PersonRow({ person, onClick }: { person: Person; onClick: () => void }) {
  const isUpdated = isUpdatedContactPerson(person);
  return (
    <button type="button" className={`person-row ${isUpdated ? "updated" : ""}`} onClick={onClick}>
      <span className={`person-avatar ${isUpdated ? "updated" : ""}`}>{person.name.slice(0, 1)}</span>
      <span className="person-row-text">
        <strong>{person.name}</strong>
        <small>{person.role || "—"} · {person.company || "—"}</small>
      </span>
      {isUpdated ? <span className="person-updated-pill">Updated</span> : null}
    </button>
  );
}

/**
 * Right-hand exploration panel. One panel, three modes (no graph reflow on click):
 *  person → full PersonCard · tag → people carrying that tag · else → match drafts.
 */
export function ExplorePanel({
  recommendations,
  selectedPerson,
  screenshotPreviews,
  onSelectPerson,
  onCloseSelection,
  onClearMatches,
}: ExplorePanelProps) {
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [mockBrief, setMockBrief] = useState<MockInterviewBriefResponse | null>(null);
  const [mockBriefError, setMockBriefError] = useState<string | null>(null);
  const [vapiError, setVapiError] = useState<string | null>(null);
  const [vapiReady, setVapiReady] = useState<MockInterviewVapiResponse | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceCallStatus>("idle");
  const [voiceProgress, setVoiceProgress] = useState<string | null>(null);
  const [voiceTurns, setVoiceTurns] = useState<VoiceTurn[]>([]);
  const [liveUserTranscript, setLiveUserTranscript] = useState("");
  const [liveAssistantTranscript, setLiveAssistantTranscript] = useState("");
  const [assistantSpeaking, setAssistantSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const vapiRef = useRef<Vapi | null>(null);
  const vapiKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY;

  useEffect(() => setApproved(new Set()), [recommendations]);
  useEffect(() => {
    const activeVapi = vapiRef.current;
    if (activeVapi) void activeVapi.stop().catch(() => null);
    setMockBrief(null);
    setMockBriefError(null);
    setVapiError(null);
    setVapiReady(null);
    setVoiceStatus("idle");
    setVoiceProgress(null);
    setVoiceTurns([]);
    setLiveUserTranscript("");
    setLiveAssistantTranscript("");
    setAssistantSpeaking(false);
    setIsMuted(false);
  }, [selectedPerson?.id]);

  useEffect(() => {
    return () => {
      const vapi = vapiRef.current;
      if (!vapi) return;
      vapi.removeAllListeners();
      void vapi.stop().catch(() => null);
      vapiRef.current = null;
    };
  }, []);

  const mode = selectedPerson ? "person" : recommendations.length ? "matches" : "none";
  if (mode === "none") return null;

  if (mode === "person" && selectedPerson) {
    const p = selectedPerson;
    const isUpdated = isUpdatedContactPerson(p);
    const screenshotUrl = screenshotUrlForPerson(p, screenshotPreviews);

    async function prepareBriefForChat() {
      setMockBriefError(null);
      try {
        if (mockBrief) return mockBrief;
        const nextBrief = await prepareMockInterview(p);
        setMockBrief(nextBrief);
        return nextBrief;
      } catch (err) {
        setMockBriefError(err instanceof Error ? err.message : "Could not prepare mock interview");
        return null;
      }
    }

    function appendVoiceTurn(role: "assistant" | "user", text: string) {
      const nextText = text.trim();
      if (!nextText) return;

      setVoiceTurns((current) => {
        const last = current[current.length - 1];
        if (last?.role === role && last.text === nextText) return current;
        return [...current, { role, text: nextText }];
      });
    }

    async function ensureVapiClient() {
      if (vapiRef.current) return vapiRef.current;
      if (!vapiKey) {
        throw new Error("NEXT_PUBLIC_VAPI_PUBLIC_KEY is not configured. Add your Vapi web key to .env and restart Next.js.");
      }

      const { default: Vapi } = await import("@vapi-ai/web");
      const client = new Vapi(vapiKey);

      client.on("call-start", () => {
        setVoiceStatus("live");
        setVoiceProgress("Voice call connected");
        setVapiError(null);
      });
      client.on("call-end", () => {
        setVoiceStatus("idle");
        setVoiceProgress("Voice call ended");
        setAssistantSpeaking(false);
        setLiveUserTranscript("");
        setLiveAssistantTranscript("");
        setIsMuted(false);
      });
      client.on("speech-start", () => setAssistantSpeaking(true));
      client.on("speech-end", () => setAssistantSpeaking(false));
      client.on("call-start-progress", (event) => {
        const progress = formatVoiceProgress(event);
        if (progress) setVoiceProgress(progress);
      });
      client.on("call-start-failed", (event) => {
        setVoiceStatus("idle");
        setVapiError(describeVapiError(event));
      });
      client.on("error", (event) => {
        setVoiceStatus("idle");
        setVapiError(describeVapiError(event));
      });
      client.on("message", (message) => {
        if (!message || typeof message !== "object") return;
        const payload = message as {
          type?: unknown;
          role?: unknown;
          transcriptType?: unknown;
          transcript?: unknown;
        };

        if (typeof payload.type !== "string" || !payload.type.startsWith("transcript")) return;
        if ((payload.role !== "assistant" && payload.role !== "user") || typeof payload.transcript !== "string") return;

        const transcript = payload.transcript.trim();
        if (!transcript) return;

        if (payload.transcriptType === "partial") {
          if (payload.role === "assistant") setLiveAssistantTranscript(transcript);
          if (payload.role === "user") setLiveUserTranscript(transcript);
          return;
        }

        appendVoiceTurn(payload.role, transcript);
        if (payload.role === "assistant") setLiveAssistantTranscript("");
        if (payload.role === "user") setLiveUserTranscript("");
      });

      vapiRef.current = client;
      return client;
    }

    async function handleStartVapiVoice() {
      setVapiError(null);
      setMockBriefError(null);
      setVapiReady(null);
      setVoiceTurns([]);
      setLiveUserTranscript("");
      setLiveAssistantTranscript("");
      setVoiceProgress("Checking microphone access");
      setVoiceStatus("preparing");

      try {
        await ensureMicrophoneAccess();

        const brief = await prepareBriefForChat();
        if (!brief) return;

        setVoiceProgress("Preparing assistant");
        const result = await validateMockInterviewWithVapi(brief, "voice");
        if (result.status !== "ready" || !result.assistant_id) {
          throw new Error(result.detail ?? result.summary);
        }

        setVapiReady(result);
        setVoiceStatus("connecting");
        setVoiceProgress("Requesting microphone and connecting");

        const vapi = await ensureVapiClient();
        await vapi.start(result.assistant_id, {
          variableValues: brief.assistant.variable_values,
        });
      } catch (err) {
        setVoiceStatus("idle");
        setVoiceProgress(null);
        setVapiError(err instanceof Error ? err.message : "Could not start Vapi voice call");
      }
    }

    async function handleStopVapiVoice() {
      const vapi = vapiRef.current;
      if (!vapi) return;

      setVoiceStatus("ending");
      setVoiceProgress("Ending call");
      try {
        await vapi.stop();
      } catch (err) {
        setVoiceStatus("idle");
        setVapiError(describeVapiError(err));
      }
    }

    function handleToggleMute() {
      const vapi = vapiRef.current;
      if (!vapi) return;
      const nextMuted = !isMuted;
      vapi.setMuted(nextMuted);
      setIsMuted(nextMuted);
    }

    return (
      <aside className="explore-panel">
        <header className="explore-head">
          <button type="button" className="explore-back" onClick={() => onSelectPerson(null)}>
            <ArrowLeft size={14} /> Back
          </button>
          <button type="button" className="explore-x" aria-label="Close" onClick={onCloseSelection}>
            <X size={14} />
          </button>
        </header>
        <div className="person-detail">
          <div className="person-detail-top">
            <span className={`person-avatar lg ${isUpdated ? "updated" : ""}`}>{p.name.slice(0, 1)}</span>
            <div>
              <h2>{p.name}</h2>
              <p>{p.role || "Unknown role"}</p>
            </div>
            {isUpdated ? <span className="person-updated-pill detail">Updated</span> : null}
          </div>
          {screenshotUrl ? (
            <a className="person-screenshot" href={screenshotUrl} target="_blank" rel="noreferrer">
              <img src={screenshotUrl} alt={`${p.name} source screenshot`} />
              <span>{screenshotFileName(p)}</span>
            </a>
          ) : null}
          <dl>
            <div><dt>Company</dt><dd>{p.company || "Unknown"}</dd></div>
            <div><dt>Location</dt><dd>{p.location || "Unknown"}</dd></div>
            <div><dt>Source</dt><dd>{sourceLabel(p.source) || "Unknown"}</dd></div>
            <div><dt>Screenshot</dt><dd>{p.raw_screenshot_ref || "Unknown"}</dd></div>
            <div><dt>How we met</dt><dd>{p.how_we_met || "Unknown"}</dd></div>
          </dl>
          <div className="person-tags">
            {p.company ? <span className="chip company"><Building2 size={11} /> {p.company}</span> : null}
            {p.interests.map((interest) => (
              <span className="chip topic" key={interest}><TagIcon size={11} /> {interest}</span>
            ))}
          </div>

          <section className="mock-interview-card">
            <div className="mock-interview-head">
              <div>
                <small>Vapi</small>
                <strong>Voice interview</strong>
              </div>
              {voiceStatus === "live" || voiceStatus === "connecting" || voiceStatus === "ending" ? (
                <div className="mock-interview-actions">
                  <button
                    type="button"
                    className="mock-interview-button secondary"
                    disabled={voiceStatus !== "live"}
                    onClick={handleToggleMute}
                  >
                    {isMuted ? <Mic size={13} /> : <MicOff size={13} />}
                    {isMuted ? "Unmute" : "Mute"}
                  </button>
                  <button
                    type="button"
                    className="mock-interview-button danger"
                    disabled={voiceStatus === "ending"}
                    onClick={() => void handleStopVapiVoice()}
                  >
                    {voiceStatus === "ending" ? <Loader2 className="spin" size={13} /> : <PhoneOff size={13} />}
                    {voiceStatus === "ending" ? "Ending" : "End call"}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="mock-interview-button"
                  disabled={voiceStatus === "preparing"}
                  onClick={() => void handleStartVapiVoice()}
                >
                  {voiceStatus === "preparing" ? <Loader2 className="spin" size={13} /> : <Mic size={13} />}
                  {voiceStatus === "preparing" ? "Preparing" : "Start voice call"}
                </button>
              )}
            </div>

            <p className="mock-interview-caption">
              Create or reuse a real Vapi assistant for this contact, then launch a live browser voice call.
            </p>

            {mockBriefError ? <p className="mock-interview-error">{mockBriefError}</p> : null}
            {vapiError ? <p className="mock-interview-error">{vapiError}</p> : null}
            {vapiReady || voiceProgress || voiceTurns.length > 0 || liveUserTranscript || liveAssistantTranscript ? (
              <div className="mock-interview-body">
                <div className={`mock-vapi-result ${voiceStatus === "live" ? "completed" : voiceStatus === "idle" ? "queued" : "ready"}`}>
                  <div className="mock-interview-block-head">
                    <h3>Live transcript</h3>
                    <span className="mock-vapi-pill">{voiceStatus}</span>
                  </div>
                  {vapiReady?.assistant_name ? <p>Assistant: {vapiReady.assistant_name}</p> : null}
                  {voiceProgress ? <p>{voiceProgress}</p> : null}
                  {assistantSpeaking ? <p>Assistant is speaking…</p> : null}
                  {voiceTurns.length > 0 ? (
                    <div className="mock-voice-transcript">
                      {voiceTurns.map((turn, index) => (
                        <div className={`mock-voice-turn ${turn.role}`} key={`${turn.role}-${index}-${turn.text}`}>
                          <strong>{turn.role === "assistant" ? "Assistant" : "You"}</strong>
                          <p>{turn.text}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {liveAssistantTranscript ? (
                    <div className="mock-voice-turn assistant live">
                      <strong>Assistant</strong>
                      <p>{liveAssistantTranscript}</p>
                    </div>
                  ) : null}
                  {liveUserTranscript ? (
                    <div className="mock-voice-turn user live">
                      <strong>You</strong>
                      <p>{liveUserTranscript}</p>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      </aside>
    );
  }

  // matches mode
  return (
    <aside className="explore-panel">
      <header className="explore-head">
        <div className="explore-title">
          <Sparkles size={16} className="spark" />
          <div>
            <small>Matchmaker</small>
            <strong>Intro drafts</strong>
          </div>
        </div>
        <button type="button" className="explore-x" aria-label="Dismiss matches" onClick={onClearMatches}>
          <X size={14} />
        </button>
      </header>
      <div className="draft-list">
        {recommendations.slice(0, 3).map((item, index) => {
          const isApproved = approved.has(item.person.id);
          return (
            <article className="draft-item" key={item.person.id}>
              <div className="draft-item-head">
                <span className="draft-rank">{index + 1}</span>
                <button type="button" className="draft-name" onClick={() => onSelectPerson(item.person)}>
                  {item.person.name}
                </button>
              </div>
              <p className="draft-reason">{item.reason}</p>
              <em className="draft-message">{item.draft_message}</em>
              <div className="draft-actions">
                <button
                  type="button"
                  className="draft-copy"
                  onClick={() => void navigator.clipboard?.writeText(item.draft_message)}
                >
                  <Copy size={12} /> Copy
                </button>
                {isApproved ? (
                  <span className="draft-approved"><Check size={13} /> Approved</span>
                ) : (
                  <button
                    type="button"
                    className="draft-approve"
                    onClick={() => setApproved((s) => new Set(s).add(item.person.id))}
                  >
                    Approve
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </aside>
  );
}
