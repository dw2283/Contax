import { ArrowLeft, Building2, Check, Copy, Loader2, Mic, Sparkles, Tag as TagIcon, X } from "lucide-react";
import { useEffect, useState } from "react";
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
  const [vapiResult, setVapiResult] = useState<MockInterviewVapiResponse | null>(null);
  const [vapiError, setVapiError] = useState<string | null>(null);
  const [isRunningVapiChat, setIsRunningVapiChat] = useState(false);
  useEffect(() => setApproved(new Set()), [recommendations]);
  useEffect(() => {
    setMockBrief(null);
    setMockBriefError(null);
    setVapiResult(null);
    setVapiError(null);
    setIsRunningVapiChat(false);
  }, [selectedPerson?.id]);

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

    async function handleRunVapiChat() {
      setVapiResult(null);
      setVapiError(null);
      setMockBriefError(null);
      setIsRunningVapiChat(true);

      try {
        const brief = await prepareBriefForChat();
        if (!brief) return;

        const result = await validateMockInterviewWithVapi(brief, "chat");
        setVapiResult(result);
      } catch (err) {
        setVapiError(err instanceof Error ? err.message : "Could not run Vapi chat");
      } finally {
        setIsRunningVapiChat(false);
      }
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
                <strong>Assistant chat</strong>
              </div>
              <button
                type="button"
                className="mock-interview-button"
                disabled={isRunningVapiChat}
                onClick={() => void handleRunVapiChat()}
              >
                {isRunningVapiChat ? <Loader2 className="spin" size={13} /> : <Mic size={13} />}
                {isRunningVapiChat ? "Running" : "Start Vapi chat"}
              </button>
            </div>

            <p className="mock-interview-caption">
              Create or reuse a real Vapi assistant for this contact, then run a quick chat against it.
            </p>

            {mockBriefError ? <p className="mock-interview-error">{mockBriefError}</p> : null}
            {vapiError ? <p className="mock-interview-error">{vapiError}</p> : null}
            {vapiResult ? (
              <div className="mock-interview-body">
                <div className={`mock-vapi-result ${vapiResult.status}`}>
                  <div className="mock-interview-block-head">
                    <h3>Assistant reply</h3>
                    <span className="mock-vapi-pill">{vapiResult.status}</span>
                  </div>
                  {vapiResult.assistant_name ? <p>Assistant: {vapiResult.assistant_name}</p> : null}
                  {vapiResult.assistant_reply ? <pre>{vapiResult.assistant_reply}</pre> : <p>{vapiResult.summary}</p>}
                  {vapiResult.detail ? <p>{vapiResult.detail}</p> : null}
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
