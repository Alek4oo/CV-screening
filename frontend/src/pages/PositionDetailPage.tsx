/**
 * A position: upload and explanation on the left, the ranking always beside it.
 *
 * The ranking is a permanent part of the layout, not a panel that can be shut.
 * A recruiter reading one candidate's factors can see where that candidate sits
 * among the rest without a click — and there is no state in which the screen
 * shows a score with the field it was scored against hidden away.
 *
 * The summary under the upload is deliberately short. The full case — every
 * factor, the profile, the audit trail — lives on the candidate page, next to
 * the panel where a person decides.
 *
 * The ruleset picker is not a convenience. Every decision points at the version
 * of the rules it was taken under, so "show me the ranking as it stood under
 * 2026.07" is what makes that record checkable rather than merely stored.
 */

import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAsync } from "../hooks";
import { Loading, Notice } from "../components/common";
import { CvDropzone, type RankedUpload } from "../components/CvDropzone";
import { RoleRankingList } from "../components/RoleRankingList";
import { UploadSummary } from "../components/UploadSummary";
import type { RulesetRef } from "../api/types";

export function PositionDetailPage() {
  const { roleId = "" } = useParams();
  const navigate = useNavigate();
  const [lastUpload, setLastUpload] = useState<RankedUpload | null>(null);
  // "" means the default: the most recently activated ruleset the role was
  // ranked under. The backend picks it, so the screen does not have to guess.
  const [rulesetVersion, setRulesetVersion] = useState("");

  const role = useAsync(() => api.getRole(roleId), [roleId]);
  const ranking = useAsync(
    () => api.listRankings(roleId, rulesetVersion ? { ruleset_version: rulesetVersion } : {}),
    [roleId, rulesetVersion],
  );

  if (role.loading && !role.data) return <Loading what="the position" />;

  const title = ranking.data?.role_title ?? role.data?.title ?? "Position";
  // The client asks for 200 rows. Past that the list is a lie by omission
  // unless it says so.
  const truncated = (ranking.data?.total ?? 0) - (ranking.data?.rows.length ?? 0);

  return (
    <>
      <div className="position-layout">
        <div className="position-main">
          <div className="breadcrumb">
            <Link to="/">Positions</Link> / {role.data?.title ?? "…"}
          </div>

          <div className="page-head">
            <h1>{title}</h1>
          </div>

          {role.error && <Notice kind="error">{role.error}</Notice>}
          {ranking.error && <Notice kind="error">{ranking.error}</Notice>}

          <CvDropzone
            roleId={roleId}
            onRanked={(result) => {
              setLastUpload(result);
              // Scoring runs under the active ruleset. If an older version is on
              // screen the new candidate would not be in it, so go back to the
              // default rather than leave the upload apparently missing.
              if (rulesetVersion) setRulesetVersion("");
              else ranking.reload();
            }}
          />

          <UploadSummary roleId={roleId} result={lastUpload} />
        </div>

        <aside className="ranking-sidebar">
          <div className="card ranking-panel">
            <div className="ranking-head">
              <h2>Ranking</h2>
              <RulesetPicker
                available={ranking.data?.available_rulesets ?? []}
                selected={ranking.data?.ruleset?.version ?? ""}
                onSelect={setRulesetVersion}
              />
            </div>

            <p className="card-note">
              Every candidate scored against this position, highest first.
            </p>

            {ranking.loading && !ranking.data ? (
              <Loading what="the ranking" />
            ) : (
              <RoleRankingList
                rows={ranking.data?.rows ?? []}
                onOpen={(candidateId) => navigate(`/roles/${roleId}/candidates/${candidateId}`)}
              />
            )}

            {truncated > 0 && (
              <p className="small muted ranking-truncated">
                Showing the first {ranking.data?.rows.length} of {ranking.data?.total}. Narrow the
                field to see the rest.
              </p>
            )}

            <p className="ai-notice">
              AI-assisted. The recruiter makes the decision — the system rejects no one on its own.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}

/**
 * Which version of the rules the ranking is read under.
 *
 * Only versions this role has actually been ranked under are offered — the
 * backend returns exactly those. With a single version there is nothing to
 * choose, so the picker states it instead of showing a select of one.
 */
function RulesetPicker({
  available,
  selected,
  onSelect,
}: {
  available: RulesetRef[];
  selected: string;
  onSelect: (version: string) => void;
}) {
  if (!available.length) return null;

  if (available.length === 1) {
    return <span className="ruleset-tag">Ruleset {available[0].version}</span>;
  }

  return (
    <label className="ruleset-picker">
      <span className="small muted">Ruleset</span>
      <select value={selected} onChange={(event) => onSelect(event.target.value)}>
        {available.map((ruleset) => (
          <option key={ruleset.id} value={ruleset.version}>
            {ruleset.version}
          </option>
        ))}
      </select>
    </label>
  );
}
