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

/** Top toolbar: brand + nav on the left, the core actions in the middle, Weave trace on the right. */
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
    <header className="graph-upload-toolbar">
      <div className="toolbar-brand">
        <span className="brand-logo">
          <Image src="/logo-contax.png" alt="" width={28} height={28} priority />
        </span>
        <span className="brand-name">Contax AI</span>
        <span className="brand-divider" />
        <nav className="app-nav">
          <span className="nav-link active"><Network size={13} /> Graph</span>
          <Link href="/monitor" className="nav-link"><Activity size={13} /> Monitor</Link>
        </nav>
        <span className="toolbar-status">
          <span className="status-dot" />
          {peopleCount} people · {displayStatus}
        </span>
      </div>

      <div className="upload-cluster">
        <label className={`upload-button primary-action upload-new-contacts ${isBusy ? "disabled" : ""}`}>
          {isBusy ? <Loader2 className="spin" size={14} /> : <Upload size={14} />}
          <span>{isSeeding ? "Preparing graph" : isIngesting ? "Processing" : "Upload contacts"}</span>
          <input accept="image/*" disabled={isBusy} multiple type="file" onChange={onChooseFiles} />
        </label>
        <button className="toolbar-button" type="button" disabled={isBusy} onClick={onSeedDemo}>
          <Plus size={13} />
          Load demo
        </button>
        <button className="toolbar-button" type="button" onClick={onClearHighlights}>
          <X size={13} />
          Clear
        </button>
      </div>

      <div className="trace-actions">
        {traceUrl ? (
          <a href={traceUrl} title="Open latest Weave trace">
            <Activity size={13} />
            View trace in Weave
            <ExternalLink size={11} />
          </a>
        ) : (
          <span><Activity size={13} /> Trace appears after ingest or match</span>
        )}
      </div>
    </header>
  );
}
