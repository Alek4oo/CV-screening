/**
 * Качване на CV-та от изгледа на рекрутера, с оценка на момента.
 *
 * Всеки файл минава по своя път — качване → OCR и парсване → класиране спрямо
 * ролята — и показва резултата си веднага, вместо да чака останалите. Затова
 * обработката е последователна: OCR-ът е скъп, а десет едновременни заявки биха
 * забавили и първия резултат.
 *
 * Скорът се появява до файла секунди след пускането му, но не мести никого по
 * потока. Новият кандидат влиза в класацията със статус „за преглед" — както
 * всеки друг, защото решението е на човек.
 */

import { useCallback, useRef, useState, type DragEvent } from "react";
import { ApiError, api } from "../api/client";
import { ACCEPTED_EXTENSIONS, formatBytes, normaliseFile, validateFile } from "../api/upload";
import { formatPercent, formatScore } from "../api/labels";
import type { ExtractionInfo } from "../api/types";
import { MinimumBadge, Notice } from "./common";
import { Link } from "react-router-dom";

type Stage = "queued" | "reading" | "scoring" | "done" | "failed";

interface Item {
  id: string;
  name: string;
  size: number;
  stage: Stage;
  error?: string;
  extraction?: ExtractionInfo;
  candidateName?: string;
  rankingId?: string;
  score?: number;
  meetsMinimum?: boolean;
}

const STAGE_LABELS: Record<Stage, string> = {
  queued: "Queued",
  reading: "Reading the document…",
  scoring: "Scoring…",
  done: "Done",
  failed: "Rejected",
};

/** Под този праг парсерът е намерил малко секции — рекрутерът да провери. */
const LOW_CONFIDENCE = 0.5;

interface Props {
  roleId: string;
  roleTitle: string;
  /** Извиква се, след като партидата приключи — таблицата се презарежда. */
  onIngested: () => void;
}

export function CvUpload({ roleId, roleTitle, onIngested }: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const update = useCallback((id: string, patch: Partial<Item>) => {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );
  }, []);

  const process = useCallback(
    async (files: File[]) => {
      if (!files.length) return;

      const queued: Item[] = files.map((file, index) => ({
        id: `${Date.now()}-${index}-${file.name}`,
        name: file.name,
        size: file.size,
        stage: "queued",
      }));
      setItems((current) => [...queued, ...current]);
      setBusy(true);

      let ingested = false;

      for (const [index, file] of files.entries()) {
        const { id } = queued[index];

        const problem = validateFile(file);
        if (problem) {
          // Отказва се преди мрежата — няма смисъл да пътува файл, който знаем,
          // че ще се върне с 415 или 413.
          update(id, { stage: "failed", error: problem });
          continue;
        }

        // Кой от двата хода е гръмнал — качването или класирането. Държи се
        // локално, а не се чете от състоянието: съобщението за рекрутера е
        // различно и не бива да зависи от това дали React вече е пребоядисал.
        let stored = false;

        try {
          update(id, { stage: "reading" });
          const uploaded = await api.uploadCandidate(normaliseFile(file));
          stored = true;
          ingested = true;

          update(id, {
            stage: "scoring",
            extraction: uploaded.extraction,
            candidateName: uploaded.candidate.full_name,
          });

          const ranked = await api.rank(roleId, { candidateIds: [uploaded.candidate.id] });
          const result = ranked.ranked[0];

          update(id, {
            stage: "done",
            rankingId: result?.ranking_id,
            score: result?.score,
            meetsMinimum: result?.meets_minimum,
          });
        } catch (cause) {
          const message = cause instanceof ApiError ? cause.message : String(cause);
          update(id, {
            stage: "failed",
            error: stored
              ? `The CV was uploaded, but scoring failed: ${message}`
              : message,
          });
        }
      }

      setBusy(false);
      if (ingested) onIngested();
    },
    [roleId, onIngested, update],
  );

  function pick(fileList: FileList | null) {
    if (fileList) void process(Array.from(fileList));
    if (inputRef.current) inputRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!busy) pick(event.dataTransfer.files);
  }

  const failed = items.filter((item) => item.stage === "failed").length;

  return (
    <div className="card">
      <h2>Upload CVs</h2>
      <p className="card-note">
        PDF (scanned included) or TXT, up to 10 MB. Every file is read, parsed and scored against
        “{roleTitle}” straight away — the result appears below.
      </p>

      <div
        className={`dropzone${dragging ? " dragging" : ""}${busy ? " busy" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          id="cv-files"
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS}
          disabled={busy}
          onChange={(event) => pick(event.target.files)}
        />
        <label htmlFor="cv-files" className="dropzone-label">
          <strong>Drop the files here</strong>
          <span>or pick them from disk · PDF, TXT</span>
        </label>
      </div>

      {items.length > 0 && (
        <>
          <ul className="upload-list">
            {items.map((item) => (
              <UploadRow key={item.id} item={item} />
            ))}
          </ul>

          <div className="decision-actions">
            <button type="button" onClick={() => setItems([])} disabled={busy}>
              Clear the list
            </button>
            {failed > 0 && (
              <span className="small muted">
                {failed} {failed === 1 ? "file was not accepted" : "files were not accepted"}. The
                rest are in the ranking.
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function UploadRow({ item }: { item: Item }) {
  const working = item.stage === "reading" || item.stage === "scoring";
  const lowConfidence =
    item.extraction !== undefined && item.extraction.confidence < LOW_CONFIDENCE;

  return (
    <li className={`upload-item ${item.stage}`}>
      <div className="upload-head">
        <span className="file">
          <strong>{item.name}</strong>
          <span className="small muted"> · {formatBytes(item.size)}</span>
        </span>

        <span className="upload-stage">
          {working && <span className="spinner" aria-hidden="true" />}
          {item.stage === "done" && item.score !== undefined ? (
            <>
              <span className="upload-score">{formatScore(item.score)} pts</span>
              {item.meetsMinimum !== undefined && <MinimumBadge meets={item.meetsMinimum} />}
            </>
          ) : (
            <span className="small muted">{STAGE_LABELS[item.stage]}</span>
          )}
        </span>
      </div>

      {item.error && (
        <Notice kind="error">{item.error}</Notice>
      )}

      {item.extraction && !item.error && (
        <div className="small muted upload-meta">
          {item.candidateName && <>Read as <strong>{item.candidateName}</strong> · </>}
          {item.extraction.engine} · {item.extraction.characters} characters · parse confidence{" "}
          {formatPercent(item.extraction.confidence)}
          {item.rankingId && (
            <>
              {" · "}
              <Link to={`/rankings/${item.rankingId}`}>see the explanation</Link>
            </>
          )}
        </div>
      )}

      {lowConfidence && item.stage === "done" && (
        <Notice kind="warn">
          The parser recognised few sections. Check the profile in the detail view before deciding
          on the score — the CV may be in an unusual format.
        </Notice>
      )}
    </li>
  );
}
