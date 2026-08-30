/**
 * The short explanation for the CV that was just uploaded.
 *
 * A summary, not the full case: name, score, and one line per factor with what
 * was matched and what is missing. Enough for the recruiter to see why the
 * number came out as it did without leaving the position — and a link to the
 * candidate page, where the full breakdown sits next to the decision panel.
 *
 * The "meets minimum" badge appears only when it is true. There is no opposite
 * label here for the same reason as in the ranking: on a screen with no
 * decision controls, a red verdict does the work of an automatic rejection.
 */

import { Link } from "react-router-dom";
import { factorLabel, formatPercent, formatScore } from "../api/labels";
import type { RankedUpload } from "./CvDropzone";

interface Props {
  roleId: string;
  /** null until a CV has been uploaded — the area stays empty until then. */
  result: RankedUpload | null;
}

export function UploadSummary({ roleId, result }: Props) {
  if (!result) return null;

  const { ranked, candidateName, candidateId } = result;

  return (
    <section className="card upload-summary">
      <div className="summary-head">
        <div>
          <h2>{candidateName}</h2>
          <div className="small muted">Just added · for review</div>
        </div>

        <div className="summary-score">
          {formatScore(ranked.score)}
          <span className="of">/ 100</span>
        </div>
      </div>

      {ranked.meets_minimum && <span className="badge ok">Meets minimum</span>}

      {ranked.factors.length ? (
        <div className="summary-factors">
          {[...ranked.factors]
            .sort((left, right) => right.weight - left.weight)
            .map((factor) => (
              <div className="summary-factor" key={factor.name}>
                <div className="summary-factor-head">
                  <span className="name">{factorLabel(factor.name)}</span>
                  <span className="percent">{formatPercent(factor.subscore)}</span>
                </div>

                {(factor.matched.length > 0 || factor.missing.length > 0) && (
                  <div className="chips">
                    {factor.matched.map((skill) => (
                      <span key={`matched-${skill}`} className="chip matched" title="Covered">
                        {skill}
                      </span>
                    ))}
                    {factor.missing.map((skill) => (
                      <span key={`missing-${skill}`} className="chip missing" title="Missing">
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
        </div>
      ) : (
        <p className="muted small">
          This position has no requirements to score against.
        </p>
      )}

      <Link className="summary-link" to={`/roles/${roleId}/candidates/${candidateId}`}>
        See the full explanation
      </Link>
    </section>
  );
}
