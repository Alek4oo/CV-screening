/**
 * Детайл на кандидат: защо е класиран така и решението по него.
 *
 * Лявата колона е обяснението (скор, фактори, профил), дясната — какво иска
 * ролята, кой е решил и одитната следа. Разделението не е само оформление:
 * рекрутерът трябва да види изискванията до профила, преди да натисне бутон.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import {
  RULESET_STATUS_LABELS,
  factorLabel,
  formatDateTime,
  OUTCOME_LABELS,
} from "../api/labels";
import type { Decision, DecisionOutcome, RoleRequirements } from "../api/types";
import { useAsync, useRecruiter } from "../hooks";
import { Chips, Loading, MinimumBadge, Notice } from "../components/common";
import { FactorBreakdown, ScoreHeadline } from "../components/Explanation";
import { DecisionPanel } from "../components/DecisionPanel";
import { CandidateProfileCard } from "../components/CandidateProfile";

export function RankingDetailPage() {
  // Two ways in. The position screen sends a recruiter to a candidate of a
  // role, so its route carries the pair of ids a person actually sees; the
  // older leaderboard links straight to a ranking. Both land here.
  const { rankingId = "", roleId = "", candidateId = "" } = useParams();
  const [recruiter] = useRecruiter();
  const [decision, setDecision] = useState<Decision | null | undefined>(undefined);

  const detail = useAsync(
    () =>
      rankingId
        ? api.getRanking(rankingId)
        : api.getRankingForCandidate(roleId, candidateId),
    [rankingId, roleId, candidateId],
  );

  // The audit is keyed by the ranking, which is only known once the detail has
  // loaded — on the candidate route it is not in the URL.
  const resolvedId = detail.data?.ranking_id ?? "";
  const [auditNonce, setAuditNonce] = useState(0);
  const audit = useAsync(
    () => (resolvedId ? api.getRankingAudit(resolvedId) : Promise.resolve([])),
    [resolvedId, auditNonce],
  );

  if (detail.error) return <Notice kind="error">{detail.error}</Notice>;
  if (!detail.data) return <Loading what="the candidate" />;

  const data = detail.data;
  // Прясно записаното решение изпреварва заредения детайл, за да не мига UI-ът.
  const current = decision === undefined ? data.decision : decision;

  return (
    <>
      <div className="breadcrumb">
        <Link to="/">Positions</Link> /{" "}
        <Link to={`/roles/${data.role.id}`}>{data.role.title}</Link> / {data.candidate.full_name}
      </div>

      <div className="page-head">
        <div>
          <h1>{data.candidate.full_name}</h1>
          <div className="subtitle">
            {data.candidate.email ?? "no email"}
            {data.candidate.source_filename ? ` · ${data.candidate.source_filename}` : ""}
          </div>
        </div>
      </div>

      <div className="grid-two">
        <div>
          <div className="card">
            <h2>Result</h2>
            <p className="card-note">
              Computed in <strong>{data.mode}</strong> mode by the{" "}
              <strong>{data.engine || "unknown"}</strong> adapter under ruleset{" "}
              <strong>{data.ruleset.version}</strong>. Scoring has no access to the candidate’s
              protected attributes.
            </p>

            <ScoreHeadline score={data.score} position={data.position} />

            <div style={{ marginTop: 14 }}>
              <MinimumBadge meets={data.meets_minimum} />
            </div>

            {!data.meets_minimum && (
              <Notice kind="warn">
                The candidate does not meet every hard requirement of the role. This is a flag for
                review, not a refusal — the decision stays yours.
              </Notice>
            )}
          </div>

          <div className="card">
            <h2>Why this result</h2>
            <p className="card-note">
              Each factor contributes points according to its weight in the ruleset and how much of
              the requirement is met.
            </p>
            <FactorBreakdown factors={data.factors} />
          </div>

          <CandidateProfileCard candidate={data.candidate} />
        </div>

        <div>
          <DecisionPanel
            rankingId={data.ranking_id}
            decision={current}
            recruiter={recruiter}
            onRecorded={(recorded) => {
              setDecision(recorded);
              setAuditNonce((value) => value + 1);
            }}
          />

          <RequirementsCard requirements={data.role.requirements} title={data.role.title} />

          <div className="card">
            <h2>Ruleset</h2>
            <dl className="definition-list">
              <dt>Version</dt>
              <dd>
                {data.ruleset.version} · {RULESET_STATUS_LABELS[data.ruleset.status]}
              </dd>
              <dt>Name</dt>
              <dd>{data.ruleset.name}</dd>
              {Object.entries(data.weights).map(([name, weight]) => (
                <RuleWeight key={name} name={name} weight={weight} />
              ))}
            </dl>
            <p className="card-note" style={{ marginTop: 12, marginBottom: 0 }}>
              The decision points at this version. New rules produce a new ranking; the old one stays
              for the audit.
            </p>
          </div>

          <div className="card">
            <h2>Audit trail</h2>
            <p className="card-note">Who, when and what — exactly as recorded in the log.</p>
            {audit.loading && !audit.data ? (
              <Loading what="the audit trail" />
            ) : !audit.data?.length ? (
              <p className="muted small">No entries.</p>
            ) : (
              <ul className="timeline">
                {audit.data.map((entry) => (
                  <li key={entry.id}>
                    <div>
                      <strong>{describeAction(entry.action)}</strong> · {entry.actor}
                    </div>
                    <div className="when">{formatDateTime(entry.occurred_at)}</div>
                    {typeof entry.payload_in.rationale === "string" && (
                      <div className="small">“{entry.payload_in.rationale}”</div>
                    )}
                    {typeof entry.payload_out.previous_outcome === "string" && (
                      <div className="small muted">
                        {OUTCOME_LABELS[entry.payload_out.previous_outcome as DecisionOutcome]} →{" "}
                        {OUTCOME_LABELS[entry.payload_in.outcome as DecisionOutcome]}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function RuleWeight({ name, weight }: { name: string; weight: number }) {
  return (
    <>
      <dt>{factorLabel(name)}</dt>
      <dd>{weight}</dd>
    </>
  );
}

function RequirementsCard({
  requirements,
  title,
}: {
  requirements: RoleRequirements;
  title: string;
}) {
  const names = (list: RoleRequirements["required_skills"]) =>
    (list ?? []).map((item) => (typeof item === "string" ? item : item.name));

  return (
    <div className="card">
      <h2>What the role requires</h2>
      <p className="card-note">{title}</p>
      <dl className="definition-list">
        <dt>Required</dt>
        <dd>
          <Chips items={names(requirements.required_skills)} />
        </dd>
        <dt>Preferred</dt>
        <dd>
          <Chips items={names(requirements.preferred_skills)} />
        </dd>
        <dt>Experience</dt>
        <dd>
          {requirements.min_years_experience
            ? `at least ${requirements.min_years_experience} yrs`
            : "no requirement"}
        </dd>
        <dt>Education</dt>
        <dd>{requirements.min_degree ?? "no requirement"}</dd>
        <dt>Languages</dt>
        <dd>
          <Chips items={requirements.languages ?? []} />
        </dd>
      </dl>
    </div>
  );
}

const ACTION_LABELS: Record<string, string> = {
  cv_ingested: "CV ingested",
  profile_parsed: "Profile parsed",
  candidate_scored: "Scored",
  decision_recorded: "Decision recorded",
  bias_audit_run: "Bias audit",
};

function describeAction(action: string): string {
  return ACTION_LABELS[action] ?? action;
}
