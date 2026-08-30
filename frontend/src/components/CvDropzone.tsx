/**
 * The upload zone on the position screen.
 *
 * One CV at a time: the file is uploaded, read and scored against the position.
 * The result goes to the screen, which reloads the ranking and shows the short
 * explanation underneath. Scoring records no decision — the candidate arrives
 * for review, like everyone else.
 *
 * Accepts PDF (scanned included, via OCR) and TXT — exactly what the backend
 * lets through. If it ever accepts images too, that is a change to
 * `allowed_upload_types` in `backend/app/core/config.py` and to the constants
 * in `api/upload.ts`; the hint below reads from them.
 */

import { useRef, useState, type DragEvent } from "react";
import { ApiError, api } from "../api/client";
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_BYTES, formatBytes, normaliseFile, validateFile } from "../api/upload";
import type { RankedCandidate } from "../api/types";
import { Notice } from "./common";

/** What the screen needs to summarise the upload it just made. */
export interface RankedUpload {
  candidateId: string;
  candidateName: string;
  ranked: RankedCandidate;
}

interface Props {
  roleId: string;
  /** Called once the new candidate is scored: reload the ranking, show a summary. */
  onRanked: (result: RankedUpload) => void;
}

type Stage = "idle" | "reading" | "scoring";

const STAGE_LABELS: Record<Exclude<Stage, "idle">, string> = {
  reading: "Reading the document…",
  scoring: "Scoring…",
};

export function CvDropzone({ roleId, onRanked }: Props) {
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const busy = stage !== "idle";

  async function process(file: File) {
    setError(null);

    const problem = validateFile(file);
    if (problem) {
      // Refused before the network — no point sending a file we know comes
      // back as 415 or 413.
      setError(problem);
      return;
    }

    // Which of the two steps failed. Held locally because the message differs:
    // an uploaded-but-unscored candidate already exists in the database.
    let stored = false;

    try {
      setStage("reading");
      const uploaded = await api.uploadCandidate(normaliseFile(file));
      stored = true;

      setStage("scoring");
      const response = await api.rank(roleId, { candidateIds: [uploaded.candidate.id] });
      const ranked = response.ranked[0];

      if (!ranked) {
        setError("The CV was uploaded, but no ranking came back for it.");
        return;
      }

      onRanked({
        candidateId: uploaded.candidate.id,
        candidateName: uploaded.candidate.full_name,
        ranked,
      });
    } catch (cause) {
      const message = cause instanceof ApiError ? cause.message : String(cause);
      setError(stored ? `The CV was uploaded, but scoring failed: ${message}` : message);
    } finally {
      setStage("idle");
    }
  }

  function pick(files: FileList | null) {
    const file = files?.[0];
    if (file) void process(file);
    if (inputRef.current) inputRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!busy) pick(event.dataTransfer.files);
  }

  return (
    <div className="card">
      <h2>Add a CV</h2>

      <div
        className={`dropzone big${dragging ? " dragging" : ""}${busy ? " busy" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          id="cv-file"
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          disabled={busy}
          onChange={(event) => pick(event.target.files)}
        />
        <label htmlFor="cv-file" className="dropzone-label">
          <DocumentIcon />
          <strong>Drop a CV here or click</strong>
          <span>PDF (scanned included) or TXT, up to {formatBytes(MAX_UPLOAD_BYTES)}</span>
        </label>
      </div>

      {busy && (
        <div className="upload-progress">
          <span className="spinner" aria-hidden="true" />
          <span className="small muted">{STAGE_LABELS[stage as Exclude<Stage, "idle">]}</span>
        </div>
      )}

      {error && <Notice kind="error">{error}</Notice>}
    </div>
  );
}

/** A document icon, inline so a single SVG does not become a dependency. */
function DocumentIcon() {
  return (
    <svg
      className="dropzone-icon"
      viewBox="0 0 24 24"
      width="34"
      height="34"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 3v5h5" />
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M12 12v5" />
      <path d="M9.5 14.5 12 12l2.5 2.5" />
    </svg>
  );
}
