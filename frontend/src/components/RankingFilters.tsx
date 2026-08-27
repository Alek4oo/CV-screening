/**
 * Филтрите над класацията.
 *
 * Всички стесняват показаното, никой не мени статус. Затова и „не покрива
 * минимума" е филтър като всеки друг — рекрутерът може да го включи, за да
 * прегледа точно тези кандидати, вместо системата да ги скрие вместо него.
 */

import type { RankingFilters as Filters, DecisionOutcome, RulesetRef } from "../api/types";
import { OUTCOMES, OUTCOME_LABELS, RULESET_STATUS_LABELS } from "../api/labels";

interface Props {
  filters: Filters;
  onChange: (next: Filters) => void;
  rulesets: RulesetRef[];
  counts: Record<DecisionOutcome, number>;
  total: number;
  totalUnfiltered: number;
}

const SORT_LABELS: Record<NonNullable<Filters["sort"]>, string> = {
  score_desc: "Score — high to low",
  score_asc: "Score — low to high",
  name_asc: "Name — A to Z",
  name_desc: "Name — Z to A",
};

export function RankingFiltersBar({
  filters,
  onChange,
  rulesets,
  counts,
  total,
  totalUnfiltered,
}: Props) {
  const patch = (next: Partial<Filters>) => onChange({ ...filters, ...next });

  const activeOutcome = filters.outcome ?? "";
  // Версията правила не е филтър, а кой изглед се гледа — не се чисти с тях.
  const hasFilters = Boolean(
    filters.q?.trim() ||
      filters.outcome ||
      filters.meets_minimum !== null ||
      filters.min_score !== null ||
      filters.max_score !== null,
  );

  return (
    <>
      <div className="status-bar" role="group" aria-label="Filter by decision status">
        <button
          type="button"
          className="status-chip"
          aria-pressed={activeOutcome === ""}
          onClick={() => patch({ outcome: "" })}
        >
          All <span className="count">{totalUnfiltered}</span>
        </button>
        {OUTCOMES.map((outcome) => (
          <button
            key={outcome}
            type="button"
            className="status-chip"
            aria-pressed={activeOutcome === outcome}
            onClick={() => patch({ outcome: activeOutcome === outcome ? "" : outcome })}
          >
            {OUTCOME_LABELS[outcome]} <span className="count">{counts[outcome] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="card">
        <div className="filters">
          <div className="field grow">
            <label htmlFor="filter-q">Search by name or email</label>
            <input
              id="filter-q"
              type="search"
              value={filters.q ?? ""}
              placeholder="e.g. Ivanova"
              onChange={(event) => patch({ q: event.target.value })}
            />
          </div>

          <div className="field">
            <label htmlFor="filter-minimum">Minimum requirements</label>
            <select
              id="filter-minimum"
              value={filters.meets_minimum === null || filters.meets_minimum === undefined
                ? ""
                : String(filters.meets_minimum)}
              onChange={(event) =>
                patch({
                  meets_minimum: event.target.value === "" ? null : event.target.value === "true",
                })
              }
            >
              <option value="">Any</option>
              <option value="true">Meets minimum</option>
              <option value="false">Minimum not met</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="filter-min-score">Score</label>
            <div className="score-range">
              <input
                id="filter-min-score"
                type="number"
                min={0}
                max={100}
                placeholder="from"
                value={filters.min_score ?? ""}
                onChange={(event) =>
                  patch({ min_score: event.target.value === "" ? null : Number(event.target.value) })
                }
              />
              <span className="muted">–</span>
              <input
                type="number"
                min={0}
                max={100}
                placeholder="to"
                aria-label="Maximum score"
                value={filters.max_score ?? ""}
                onChange={(event) =>
                  patch({ max_score: event.target.value === "" ? null : Number(event.target.value) })
                }
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="filter-sort">Sort</label>
            <select
              id="filter-sort"
              value={filters.sort ?? "score_desc"}
              onChange={(event) => patch({ sort: event.target.value as Filters["sort"] })}
            >
              {Object.entries(SORT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {rulesets.length > 1 && (
            <div className="field">
              <label htmlFor="filter-ruleset">Ruleset version</label>
              <select
                id="filter-ruleset"
                value={filters.ruleset_version ?? rulesets[0].version}
                onChange={(event) => patch({ ruleset_version: event.target.value })}
              >
                {rulesets.map((ruleset) => (
                  <option key={ruleset.id} value={ruleset.version}>
                    {ruleset.version} · {RULESET_STATUS_LABELS[ruleset.status]}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="filter-summary">
          <span>
            {hasFilters ? (
              <>
                Showing <strong>{total}</strong> of {totalUnfiltered} ranked
              </>
            ) : (
              <>
                <strong>{totalUnfiltered}</strong> candidates ranked
              </>
            )}
          </span>
          {hasFilters && (
            <button
              type="button"
              onClick={() =>
                onChange({ sort: filters.sort, ruleset_version: filters.ruleset_version })
              }
            >
              Clear filters
            </button>
          )}
        </div>
      </div>
    </>
  );
}
