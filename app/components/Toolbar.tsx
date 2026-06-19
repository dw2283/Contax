import {
  Activity,
  ExternalLink,
  Loader2,
  Network,
  Plus,
  Upload,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { ChangeEvent } from "react";

type ToolbarProps = {
  peopleCount: number;
  redisStatus: string;
  isIngesting: boolean;
  isSeeding: boolean;
  traceUrl: string | null;
  onChooseFiles: (event: ChangeEvent<HTMLInputElement>) => void;
  onSeedDemo: () => void;
  onClearHighlights: () => void;
};

function storageLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized.includes("error")) return "Storage issue";
  if (normalized.includes("off")) return "Offline";
  if (normalized.includes("fakeredis") || normalized.includes("memory")) return "Local demo";
  if (normalized.includes("redis")) return "Local Redis";
  if (normalized.includes("pending")) return "Connecting";
  return "Local demo";
}

/** Top toolbar: one upload action, Clear highlight, and Weave trace. */
export function Toolbar({
  peopleCount,
  redisStatus,
  isIngesting,
  isSeeding,
  traceUrl,
  onChooseFiles,
  onSeedDemo,
  onClearHighlights,
}: ToolbarProps) {
  const isBusy = isIngesting || isSeeding;
  const displayStatus = storageLabel(redisStatus);

  return (
    <>
      <header className="graph-upload-toolbar">
        <div className="toolbar-brand">
          <span className="brand-logo">
            <Image src="/logo-contax-c-multi-connected.png" alt="" width={44} height={44} priority />
          </span>
          <div>
            <h1>Contax AI</h1>
            <p>{peopleCount} people · {displayStatus}</p>
          </div>
          <nav className="app-nav">
            <span className="nav-link active"><Network size={15} /> Graph</span>
            <Link href="/monitor" className="nav-link"><Activity size={15} /> Monitor</Link>
          </nav>
        </div>

        <div className="upload-cluster">
          <label className={`upload-button primary-action upload-new-contacts ${isBusy ? "disabled" : ""}`}>
            {isBusy ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}
            <span>{isSeeding ? "Preparing graph" : isIngesting ? "Processing contacts" : "Upload New Contacts"}</span>
            <input accept="image/*" disabled={isBusy} multiple type="file" onChange={onChooseFiles} />
          </label>
          <button className="toolbar-button" type="button" disabled={isBusy} onClick={onSeedDemo}>
            <Plus size={15} />
            Load demo
          </button>
          <button className="toolbar-button" type="button" onClick={onClearHighlights}>
            <X size={15} />
            Clear highlight
          </button>
        </div>

        <div className="trace-actions">
          {traceUrl ? (
            <a href={traceUrl} title="Open latest Weave trace">
              <ExternalLink size={15} />
              View trace in Weave
            </a>
          ) : (
            <span><Activity size={15} /> Trace appears after ingest or match</span>
          )}
        </div>
      </header>
    </>
  );
}
