/**
 * Creating a position.
 *
 * Only the title is required — the backend accepts a role with no requirements
 * and creates it as a draft. Skills are typed comma-separated or one per line,
 * because that is how a recruiter already has them; turning that into
 * `requirements` is this component's job, not the person's at the screen.
 *
 * Focus lands on the title field because `Modal` focuses the first control in
 * the panel, which for a form is the first thing to fill in.
 */

import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Role } from "../api/types";
import { Modal } from "./Modal";
import { Notice } from "./common";

interface Props {
  onCreated: (role: Role) => void;
  onCancel: () => void;
}

/** "python, sql" and a line-per-skill list come out the same. */
function parseSkills(raw: string): string[] {
  return raw
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function NewPositionDialog({ onCreated, onCancel }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [skills, setSkills] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const trimmed = title.trim();
    if (!trimmed) {
      setError("A title is required.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const required = parseSkills(skills);
      const role = await api.createRole({
        title: trimmed,
        description: description.trim() || null,
        requirements: required.length ? { required_skills: required } : {},
      });
      onCreated(role);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
      setBusy(false);
    }
  }

  return (
    <Modal title="New position" busy={busy} onCancel={onCancel}>
      <form
        className="modal-body"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="position-title">Title</label>
        <input
          id="position-title"
          value={title}
          placeholder="e.g. Backend Developer"
          onChange={(event) => setTitle(event.target.value)}
        />

        <label htmlFor="position-description">Description (optional)</label>
        <textarea
          id="position-description"
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />

        <label htmlFor="position-skills">Required skills (optional)</label>
        <input
          id="position-skills"
          value={skills}
          placeholder="python, postgresql, docker"
          onChange={(event) => setSkills(event.target.value)}
        />
        <span className="small muted">Comma-separated. The score is computed against these.</span>

        {error && <Notice kind="error">{error}</Notice>}

        <div className="modal-actions">
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
