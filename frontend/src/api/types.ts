/**
 * Огледало на Pydantic схемите от `backend/app/api/schemas.py`.
 *
 * Няма поле `protected_attributes` и тук — както и в схемите на бекенда.
 * Признаците са вход единствено на bias-одита; изглед, който може да ги
 * получи, рано или късно ще ги покаже.
 */

export type RoleStatus = "draft" | "open" | "closed";
export type RulesetStatus = "draft" | "active" | "retired";

/** Статусите на решението — единственото, което мести кандидат по потока. */
export type DecisionOutcome = "pending" | "advanced" | "rejected" | "on_hold";

export interface Role {
  id: string;
  external_ref: string | null;
  title: string;
  description: string | null;
  requirements: RoleRequirements;
  status: RoleStatus;
  created_at: string;
  updated_at: string;
}

/** Формата, която бекендът валидира при създаване на роля. */
export interface RoleRequirements {
  required_skills?: (string | { name: string; weight?: number })[];
  preferred_skills?: (string | { name: string; weight?: number })[];
  min_years_experience?: number;
  min_degree?: string;
  languages?: string[];
}

export interface RulesetRef {
  id: string;
  version: string;
  name: string;
  status: RulesetStatus;
}

export interface Factor {
  name: string;
  /** Тежестта на фактора от версията правила. */
  weight: number;
  /** Изпълнение на фактора, 0..1 — независимо от тежестта. */
  subscore: number;
  /** Точки, които факторът дава на крайния скор. */
  contribution: number;
  matched: string[];
  missing: string[];
  detail: string;
}

export interface RankingRow {
  ranking_id: string;
  /** Място в пълната класация — не се променя от филтрите. */
  position: number;
  candidate_id: string;
  full_name: string;
  email: string | null;
  score: number;
  /** Флаг за рекрутера, не отхвърляне. */
  meets_minimum: boolean;
  top_factors: Factor[];
  missing: string[];
  outcome: DecisionOutcome;
  decided_by: string | null;
  decided_at: string | null;
  ranked_at: string;
}

export interface RankingList {
  role_id: string;
  role_title: string;
  role_status: RoleStatus;
  ruleset: RulesetRef | null;
  available_rulesets: RulesetRef[];
  mode: string;
  total: number;
  total_unfiltered: number;
  counts: Record<DecisionOutcome, number>;
  rows: RankingRow[];
}

export interface Candidate {
  id: string;
  external_ref: string | null;
  full_name: string;
  email: string | null;
  source_filename: string | null;
  profile: CandidateProfile;
  raw_text: string | null;
  created_at: string;
  updated_at: string;
}

/** Профилът варира по CV — затова всичко е по избор. */
export interface CandidateProfile {
  full_name?: string;
  contact?: Record<string, string>;
  skills?: string[];
  languages?: string[];
  experience?: {
    title?: string;
    company?: string;
    start?: string;
    end?: string;
    current?: boolean;
  }[];
  education?: { degree?: string; institution?: string; year?: string }[];
  [key: string]: unknown;
}

export interface Decision {
  id: string;
  ranking_id: string;
  ruleset_id: string;
  outcome: DecisionOutcome;
  decided_by: string | null;
  decided_at: string | null;
  rationale: string | null;
  created_at: string;
  updated_at: string;
}

export interface RankingDetail {
  ranking_id: string;
  position: number;
  score: number;
  meets_minimum: boolean;
  mode: string;
  engine: string;
  factors: Factor[];
  weights: Record<string, number>;
  candidate: Candidate;
  role: Pick<Role, "id" | "title" | "description" | "requirements" | "status">;
  ruleset: RulesetRef;
  decision: Decision | null;
  ranked_at: string;
}

export interface AuditEntry {
  id: string;
  occurred_at: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  ruleset_id: string | null;
  payload_in: Record<string, unknown>;
  payload_out: Record<string, unknown>;
}

/** Тялото на PUT /rankings/{id}/decision. И трите полета са задължителни. */
export interface DecisionWrite {
  outcome: DecisionOutcome;
  decided_by: string;
  rationale: string;
}

export interface RankingFilters {
  ruleset_version?: string;
  outcome?: DecisionOutcome | "";
  meets_minimum?: boolean | null;
  min_score?: number | null;
  max_score?: number | null;
  q?: string;
  sort?: "score_desc" | "score_asc" | "name_asc" | "name_desc";
}

/** Как е добит текстът — проследимост, не козметика. */
export interface ExtractionInfo {
  /** Името на OCR адаптера, свършил работата. */
  engine: string;
  /** Дължина на извлечения текст. */
  characters: number;
  /** Дял намерени секции при парсването, 0..1. */
  confidence: number;
}

export interface CandidateUploadResponse {
  candidate: Pick<Candidate, "id" | "full_name" | "email" | "source_filename" | "profile" | "created_at">;
  extraction: ExtractionInfo;
}

export interface RankedCandidate {
  /** Място в класацията на подадения набор — при едно CV е винаги 1. */
  position: number;
  ranking_id: string;
  candidate_id: string;
  full_name: string;
  score: number;
  meets_minimum: boolean;
  factors: Factor[];
}

export interface RankResponse {
  role_id: string;
  role_title: string;
  ruleset_id: string;
  ruleset_version: string;
  engine: string;
  mode: string;
  ranked: RankedCandidate[];
}
