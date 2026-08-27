/**
 * Класацията за избрана роля — таблицата, с която рекрутерът започва деня.
 *
 * Редът показва къде е кандидатът, колко е събрал, кои фактори са го качили и
 * какво му липсва. Никой ред не изчезва заради нисък скор: филтрите са в ръцете
 * на човека, а сортирането по скор е подредба, не отсяване.
 */

import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { factorLabel, formatDateTime, ROLE_STATUS_LABELS } from "../api/labels";
import type { RankingFilters as Filters, RankingRow } from "../api/types";
import { useAsync } from "../hooks";
import { Chips, Loading, MinimumBadge, Notice, OutcomeBadge, ScoreCell } from "../components/common";
import { RankingFiltersBar } from "../components/RankingFilters";
import { CvUpload } from "../components/CvUpload";

const EMPTY_FILTERS: Filters = {
  q: "",
  outcome: "",
  meets_minimum: null,
  min_score: null,
  max_score: null,
  sort: "score_desc",
};

export function RoleRankingPage() {
  const { roleId = "" } = useParams();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [ranking, setRanking] = useState<{ busy: boolean; error: string | null }>({
    busy: false,
    error: null,
  });

  const role = useAsync(() => api.getRole(roleId), [roleId]);
  const list = useAsync(
    () => api.listRankings(roleId, filters),
    [roleId, JSON.stringify(filters)],
  );

  const rulesets = useMemo(() => list.data?.available_rulesets ?? [], [list.data]);

  const rerank = useCallback(async () => {
    setRanking({ busy: true, error: null });
    try {
      // Преизчислението пипа само скоровете. Записаните решения остават — човек
      // ги е взел, нови правила не ги отменят.
      await api.rank(roleId);
      list.reload();
      setRanking({ busy: false, error: null });
    } catch (cause) {
      setRanking({ busy: false, error: cause instanceof Error ? cause.message : String(cause) });
    }
  }, [roleId, list]);

  if (list.loading && !list.data) return <Loading what="the ranking" />;

  return (
    <>
      <div className="breadcrumb">
        <Link to="/">Roles</Link> / {role.data?.title ?? "…"}
      </div>

      <div className="page-head">
        <div>
          <h1>{list.data?.role_title ?? role.data?.title ?? "Ranking"}</h1>
          <div className="subtitle">
            {list.data?.role_status && <>Status: {ROLE_STATUS_LABELS[list.data.role_status]} · </>}
            {list.data?.ruleset ? (
              <>
                Ruleset {list.data.ruleset.version} · {list.data.mode} mode
              </>
            ) : (
              <>Not ranked yet</>
            )}
          </div>
        </div>
        <div className="spacer" style={{ flex: 1 }} />
        <button type="button" onClick={rerank} disabled={ranking.busy}>
          {ranking.busy ? "Scoring…" : "Re-run ranking"}
        </button>
      </div>

      {ranking.error && <Notice kind="error">{ranking.error}</Notice>}
      {list.error && <Notice kind="error">{list.error}</Notice>}

      <CvUpload
        roleId={roleId}
        roleTitle={list.data?.role_title ?? role.data?.title ?? "the role"}
        onIngested={list.reload}
      />

      <RankingFiltersBar
        filters={filters}
        onChange={setFilters}
        rulesets={rulesets}
        counts={list.data?.counts ?? { pending: 0, advanced: 0, rejected: 0, on_hold: 0 }}
        total={list.data?.total ?? 0}
        totalUnfiltered={list.data?.total_unfiltered ?? 0}
      />

      <div className="card">
        {!list.data?.total_unfiltered ? (
          <div className="empty">
            No candidates have been ranked for this role yet.
            <br />
            <span className="small">
              Drop CVs in the field above — each one is read and scored straight away.
            </span>
          </div>
        ) : !list.data.rows.length ? (
          <div className="empty">No candidate matches the filters.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Candidate</th>
                  <th>Score</th>
                  <th>Minimum</th>
                  <th>Top factors</th>
                  <th>Missing</th>
                  <th>Status</th>
                  <th>Decided by</th>
                </tr>
              </thead>
              <tbody>
                {list.data.rows.map((row) => (
                  <Row
                    key={row.ranking_id}
                    row={row}
                    onOpen={() => navigate(`/rankings/${row.ranking_id}`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="muted small">
        The ranking is an aid. The final call on every candidate is made by a recruiter — the system
        rejects no one on its own.
      </p>
    </>
  );
}

function Row({ row, onOpen }: { row: RankingRow; onOpen: () => void }) {
  return (
    <tr
      onClick={onOpen}
      style={{ cursor: "pointer" }}
      onKeyDown={(event) => {
        if (event.key === "Enter") onOpen();
      }}
      tabIndex={0}
    >
      <td className="position">{row.position}</td>
      <td className="candidate-cell">
        <Link to={`/rankings/${row.ranking_id}`} onClick={(event) => event.stopPropagation()}>
          <strong>{row.full_name}</strong>
        </Link>
        {row.email && <div className="email">{row.email}</div>}
      </td>
      <td>
        <ScoreCell score={row.score} />
      </td>
      <td>
        <MinimumBadge meets={row.meets_minimum} />
      </td>
      <td>
        {row.top_factors.length ? (
          <div className="chips">
            {row.top_factors.map((factor) => (
              <span key={factor.name} className="chip">
                {factorLabel(factor.name)} +{factor.contribution.toFixed(1)}
              </span>
            ))}
          </div>
        ) : (
          <span className="muted small">—</span>
        )}
      </td>
      <td>
        <Chips items={row.missing.slice(0, 4)} kind="missing" />
      </td>
      <td>
        <OutcomeBadge outcome={row.outcome} />
      </td>
      <td className="numeric small muted">
        {row.decided_by ? (
          <>
            {row.decided_by}
            <br />
            {formatDateTime(row.decided_at)}
          </>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}
