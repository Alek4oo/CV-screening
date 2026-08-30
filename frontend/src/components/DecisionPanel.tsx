/**
 * Решението на рекрутера.
 *
 * Единственото място в изгледа, което мени статуса на кандидат, и то само след
 * като човек е избрал изход и е написал защо. Три правила държат това:
 *
 *   * Няма подразбиращ се избор — потокът не „предлага" отхвърляне на слаб скор.
 *   * Записът е блокиран без обосновка и без име на рекрутера.
 *   * Скорът не участва в решението по никакъв начин; той е контекст отляво.
 */

import { useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import { OUTCOMES, OUTCOME_HINTS, OUTCOME_LABELS, formatDateTime } from "../api/labels";
import type { Decision, DecisionOutcome } from "../api/types";
import { Notice, OutcomeBadge } from "./common";

interface Props {
  rankingId: string;
  decision: Decision | null;
  recruiter: string;
  onRecorded: (decision: Decision) => void;
}

export function DecisionPanel({ rankingId, decision, recruiter, onRecorded }: Props) {
  const current: DecisionOutcome = decision?.outcome ?? "for_review";

  const [choice, setChoice] = useState<DecisionOutcome | null>(null);
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const missingRecruiter = !recruiter.trim();
  const missingRationale = !rationale.trim();
  const canSubmit = choice !== null && !missingRecruiter && !missingRationale && !saving;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (choice === null) return;

    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const recorded = await api.putDecision(rankingId, {
        outcome: choice,
        decided_by: recruiter.trim(),
        rationale: rationale.trim(),
      });
      onRecorded(recorded);
      setChoice(null);
      setRationale("");
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2>Decision</h2>
      <p className="card-note">
        The final decision belongs to the recruiter. The system ranks and explains; it advances and
        rejects no one on its own.
      </p>

      <div className="current-decision">
        <div>
          Current status: <OutcomeBadge outcome={current} />
        </div>
        {decision?.decided_by ? (
          <>
            <div className="small muted" style={{ marginTop: 6 }}>
              {decision.decided_by} · {formatDateTime(decision.decided_at)}
            </div>
            {decision.rationale && <div className="rationale">{decision.rationale}</div>}
          </>
        ) : (
          <div className="small muted" style={{ marginTop: 6 }}>
            No one has decided on this candidate yet.
          </div>
        )}
      </div>

      {saved && <Notice kind="info">Decision saved and written to the audit log.</Notice>}
      {error && <Notice kind="error">{error}</Notice>}

      <form onSubmit={submit}>
        <label id="decision-choice-label">New decision</label>
        <div
          className="decision-choices"
          role="group"
          aria-labelledby="decision-choice-label"
        >
          {OUTCOMES.map((outcome) => (
            <button
              key={outcome}
              type="button"
              className="decision-choice"
              aria-pressed={choice === outcome}
              onClick={() => setChoice(choice === outcome ? null : outcome)}
            >
              <strong>{OUTCOME_LABELS[outcome]}</strong>
              <span>{OUTCOME_HINTS[outcome]}</span>
            </button>
          ))}
        </div>

        <label htmlFor="decision-rationale">
          Rationale <span aria-hidden="true">*</span>
        </label>
        <textarea
          id="decision-rationale"
          value={rationale}
          required
          placeholder="Why this decision? The text is stored in Decision and in the audit log."
          onChange={(event) => setRationale(event.target.value)}
        />

        <div className="decision-actions">
          <button type="submit" className="primary" disabled={!canSubmit}>
            {saving ? "Saving…" : "Save decision"}
          </button>
          <span className="small muted">
            {missingRecruiter
              ? "Enter your name at the top right — it is recorded as the decision maker."
              : choice === null
                ? "Pick a status."
                : missingRationale
                  ? "A rationale is required."
                  : `Will be recorded as ${recruiter.trim()}.`}
          </span>
        </div>
      </form>
    </div>
  );
}
