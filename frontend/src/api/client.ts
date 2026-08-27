/**
 * Тънък слой над fetch към FastAPI бекенда.
 *
 * Бекендът разделя грешките по „чия е вината" (415/413/422/409/503) и носи
 * човешко обяснение в `detail`. Затова тук не се хвърля голо `Error`, а
 * `ApiError` със статуса и текста — изгледът показва точно каквото API-то каза,
 * вместо „нещо се обърка".
 */

import type {
  AuditEntry,
  Candidate,
  CandidateUploadResponse,
  Decision,
  DecisionWrite,
  RankResponse,
  RankingDetail,
  RankingFilters,
  RankingList,
  Role,
  RoleStatus,
} from "./types";

const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Валидационните грешки на FastAPI идват като списък, не като низ. */
function messageFrom(status: number, body: unknown): string {
  if (typeof body === "string" && body.trim()) return body;

  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const lines = detail
      .map((item) => {
        const location = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "";
        return location ? `${location}: ${item?.msg}` : String(item?.msg ?? "");
      })
      .filter(Boolean);
    if (lines.length) return lines.join("; ");
  }

  return `The request failed (HTTP ${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // При multipart Content-Type се оставя на браузъра: той единствен знае
  // boundary-то, а ръчно зададена стойност го изяжда и бекендът вижда празно тяло.
  const isMultipart = init?.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        ...(isMultipart ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    // Мрежова грешка — бекендът не е стартиран или адресът е грешен. Различава
    // се от HTTP грешка, защото и лекът е различен.
    throw new ApiError(0, `No connection to the API at ${API_URL}. Is the backend running?`);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) throw new ApiError(response.status, messageFrom(response.status, body));
  return body as T;
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const serialised = search.toString();
  return serialised ? `?${serialised}` : "";
}

export const api = {
  listRoles(status?: RoleStatus): Promise<Role[]> {
    return request<Role[]>(`/roles${query({ status, limit: 200 })}`);
  },

  getRole(roleId: string): Promise<Role> {
    return request<Role>(`/roles/${roleId}`);
  },

  listRankings(roleId: string, filters: RankingFilters = {}): Promise<RankingList> {
    return request<RankingList>(
      `/roles/${roleId}/rankings${query({
        ruleset_version: filters.ruleset_version,
        outcome: filters.outcome,
        meets_minimum: filters.meets_minimum ?? undefined,
        min_score: filters.min_score ?? undefined,
        max_score: filters.max_score ?? undefined,
        q: filters.q?.trim(),
        sort: filters.sort,
        limit: 200,
      })}`,
    );
  },

  /**
   * Класира по активните правила и връща скора веднага. Не създава решения.
   *
   * `candidateIds` стеснява до току-що качените — така качването дава оценка на
   * момента, вместо да преминава през всички кандидати в базата.
   */
  rank(
    roleId: string,
    options: { rulesetVersion?: string; candidateIds?: string[] } = {},
  ): Promise<RankResponse> {
    const body: Record<string, unknown> = {};
    if (options.rulesetVersion) body.ruleset_version = options.rulesetVersion;
    if (options.candidateIds) body.candidate_ids = options.candidateIds;

    return request<RankResponse>(`/roles/${roleId}/rank`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Качва едно CV: OCR, парсване и създаване на кандидат в един ход. */
  uploadCandidate(file: File): Promise<CandidateUploadResponse> {
    const form = new FormData();
    form.append("file", file);
    return request<CandidateUploadResponse>("/candidates/upload", {
      method: "POST",
      body: form,
    });
  },

  getRanking(rankingId: string): Promise<RankingDetail> {
    return request<RankingDetail>(`/rankings/${rankingId}`);
  },

  getRankingAudit(rankingId: string): Promise<AuditEntry[]> {
    return request<AuditEntry[]>(`/rankings/${rankingId}/audit`);
  },

  /** Единственият начин кандидат да смени статус. Изисква човек и обосновка. */
  putDecision(rankingId: string, payload: DecisionWrite): Promise<Decision> {
    return request<Decision>(`/rankings/${rankingId}/decision`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  getCandidate(candidateId: string): Promise<Candidate> {
    return request<Candidate>(`/candidates/${candidateId}`);
  },
};

export { API_URL };
