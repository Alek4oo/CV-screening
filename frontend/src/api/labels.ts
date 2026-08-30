/**
 * Езикът на изгледа.
 *
 * Формулировките тук не са само превод. „Minimum not met" е нарочно избрано
 * пред „Fails requirements": PRD-то забранява автоматичното отхвърляне, а
 * надпис, който звучи като присъда, върши същото с думи.
 */

import type { DecisionOutcome, RulesetStatus } from "./types";

export const OUTCOME_LABELS: Record<DecisionOutcome, string> = {
  for_review: "For review",
  advanced: "Advanced",
  rejected: "Rejected",
  on_hold: "On hold",
};

/** Ред на статусите в лентата и в бутоните — потокът, както се минава. */
export const OUTCOMES: DecisionOutcome[] = ["for_review", "advanced", "rejected", "on_hold"];

export const OUTCOME_HINTS: Record<DecisionOutcome, string> = {
  for_review: "Back for review — no decision taken yet.",
  advanced: "Moves forward in the process.",
  rejected: "Turned down by the recruiter.",
  on_hold: "Held — the decision is deferred, not a refusal.",
};

export const RULESET_STATUS_LABELS: Record<RulesetStatus, string> = {
  draft: "Draft",
  active: "Active",
  archived: "Archived",
};

export const FACTOR_LABELS: Record<string, string> = {
  required_skills: "Required skills",
  preferred_skills: "Preferred skills",
  experience: "Work experience",
  education: "Education",
  languages: "Languages",
};

export function factorLabel(name: string): string {
  return FACTOR_LABELS[name] ?? name;
}

export function formatScore(score: number): string {
  return score.toFixed(1);
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
