import { ArrowLeft, Building2, Check, Copy, Sparkles, Tag as TagIcon, X } from "lucide-react";
import { useEffect, useState } from "react";
import { sourceLabel } from "../lib/graph";
import { isUpdatedContactPerson, screenshotFileName, screenshotUrlForPerson } from "../lib/realScreenshots";
import type { Person, Recommendation } from "../lib/types";

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
  useEffect(() => setApproved(new Set()), [recommendations]);

  const mode = selectedPerson ? "person" : recommendations.length ? "matches" : "none";
  if (mode === "none") return null;

  if (mode === "person" && selectedPerson) {
    const p = selectedPerson;
    const isUpdated = isUpdatedContactPerson(p);
    const screenshotUrl = screenshotUrlForPerson(p, screenshotPreviews);
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
