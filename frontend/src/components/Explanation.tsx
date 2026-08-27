/**
 * „Защо е класиран така" — разбивката, която прави класирането преглеждаемо.
 *
 * Показва се цялата верига: формулата, тежестта на всеки фактор от версията
 * правила, изпълнението му и точките, които е дал. Числата са същите, които
 * стоят в `ranking.explanation` — изгледът не смята нищо наум, за да не се
 * разминат екранът и одитът.
 */

import type { Factor } from "../api/types";
import { factorLabel, formatPercent, formatScore } from "../api/labels";
import { Chips } from "./common";

export function ScoreHeadline({
  score,
  position,
  total,
}: {
  score: number;
  position: number;
  total?: number;
}) {
  return (
    <div className="score-headline">
      <div>
        <div className="big">{formatScore(score)}</div>
        <div className="of">points out of 100</div>
      </div>
      <div>
        <div className="big">№{position}</div>
        <div className="of">{total ? `of ${total} ranked` : "in the ranking"}</div>
      </div>
    </div>
  );
}

export function FactorBreakdown({ factors }: { factors: Factor[] }) {
  if (!factors.length) {
    return (
      <p className="muted small">
        This role has no requirements to score against, so every candidate comes out at 0 points.
      </p>
    );
  }

  const totalWeight = factors.reduce((sum, factor) => sum + factor.weight, 0);
  const maxContribution = Math.max(...factors.map((factor) => factor.contribution), 1);

  return (
    <>
      <div className="formula">
        score = 100 × Σ(weight × fulfilment) / Σ(weight) &nbsp;·&nbsp; Σ(weight) ={" "}
        {totalWeight.toFixed(2)}
      </div>

      {[...factors]
        .sort((left, right) => right.contribution - left.contribution)
        .map((factor) => (
          <div className="factor" key={factor.name}>
            <div className="factor-head">
              <span className="name">{factorLabel(factor.name)}</span>
              <span className="weight">
                weight {factor.weight} · fulfilment {formatPercent(factor.subscore)}
              </span>
              <span className="contribution">+{formatScore(factor.contribution)} pts</span>
            </div>

            <div className="factor-bar" aria-hidden="true">
              <div style={{ width: `${(factor.contribution / maxContribution) * 100}%` }} />
            </div>

            {factor.detail && <div className="factor-detail">{factor.detail}</div>}

            <div className="factor-lists">
              <div className="row">
                <span>Matched</span>
                <Chips items={factor.matched} kind="matched" />
              </div>
              <div className="row">
                <span>Missing</span>
                <Chips items={factor.missing} kind="missing" />
              </div>
            </div>
          </div>
        ))}
    </>
  );
}
