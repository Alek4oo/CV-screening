/**
 * The ranking for one role: every candidate scored against it, best first.
 *
 * A row is a way in, not a verdict. Nobody is hidden for scoring low and
 * nothing here moves a candidate through the process — the row leads to the
 * explanation and to the panel where a person decides.
 *
 * The "meets minimum" badge shows only when it is true. The opposite label is
 * left out on purpose: on a list with no decision controls, "minimum not met"
 * reads as a refusal handed down by the machine.
 *
 * Advanced and rejected names are coloured, and that is a different thing from
 * the badge above: it reports a decision a recruiter has already recorded, not
 * a judgement the system reached on its own. Undecided candidates stay plain —
 * the ranking colours no one by score.
 */

import { OUTCOME_LABELS, formatScore } from "../api/labels";
import type { DecisionOutcome, RankingRow } from "../api/types";

interface Props {
  rows: RankingRow[];
  onOpen: (candidateId: string) => void;
}

/** Only decided outcomes get a class; for-review and on-hold stay plain. */
export function outcomeClass(outcome: DecisionOutcome): string {
  return outcome === "advanced" || outcome === "rejected" ? outcome : "";
}

export function RoleRankingList({ rows, onOpen }: Props) {
  if (!rows.length) {
    return (
      <div className="empty">
        No candidates ranked for this role yet.
        <br />
        <span className="small">Drop a CV on the left — it is read and scored straight away.</span>
      </div>
    );
  }

  return (
    <ol className="ranking-list">
      {rows.map((row) => (
        <li key={row.ranking_id}>
          <button type="button" className="ranking-row" onClick={() => onOpen(row.candidate_id)}>
            <span className="rank">№{row.position}</span>

            <span className="who">
              {/* The colour reports a decision a person already took, so it is
                  never the only carrier of that fact — the title says it in
                  words for anyone who cannot rely on the colour. */}
              <strong className={outcomeClass(row.outcome)} title={OUTCOME_LABELS[row.outcome]}>
                {row.full_name}
              </strong>
              {row.meets_minimum && <span className="badge ok">Meets minimum</span>}
            </span>

            <span className="score">
              {formatScore(row.score)}
              <span className="of">/ 100</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
