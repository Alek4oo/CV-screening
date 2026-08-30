/**
 * The position screen: the ranking sidebar, where a row leads, and the short
 * explanation an upload leaves under the drop zone.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type {
  CandidateUploadResponse,
  RankResponse,
  RankingList,
  RankingRow,
  Role,
  RulesetRef,
} from "../api/types";
import { PositionDetailPage } from "./PositionDetailPage";

const ROLE_ID = "11111111-1111-1111-1111-111111111111";
const IVAN = "22222222-2222-2222-2222-222222222222";
const MARIA = "33333333-3333-3333-3333-333333333333";

const role: Role = {
  id: ROLE_ID,
  external_ref: null,
  title: "Backend Developer",
  description: null,
  requirements: { required_skills: ["python"] },
  status: "open",
  created_at: "2026-08-27T09:00:00Z",
  updated_at: "2026-08-27T09:00:00Z",
};

function row(overrides: Partial<RankingRow> & Pick<RankingRow, "candidate_id">): RankingRow {
  return {
    ranking_id: `ranking-${overrides.candidate_id}`,
    position: 1,
    full_name: "Ivan Petrov",
    email: null,
    score: 90,
    meets_minimum: true,
    top_factors: [],
    missing: [],
    outcome: "pending",
    decided_by: null,
    decided_at: null,
    ranked_at: "2026-08-27T09:00:00Z",
    ...overrides,
  };
}

const V1: RulesetRef = { id: "rs-1", version: "2026.08.1", name: "Base", status: "active" };
const V0: RulesetRef = { id: "rs-0", version: "2026.07.1", name: "Previous", status: "retired" };

function list(rows: RankingRow[], rulesets = [V1]): RankingList {
  return {
    role_id: ROLE_ID,
    role_title: role.title,
    role_status: "open",
    ruleset: rulesets[0] ?? null,
    available_rulesets: rulesets,
    mode: "masked",
    total: rows.length,
    total_unfiltered: rows.length,
    counts: { pending: rows.length, advanced: 0, rejected: 0, on_hold: 0 },
    rows,
  };
}

const twoRows = [
  row({ candidate_id: IVAN, full_name: "Ivan Petrov", position: 1, score: 90, meets_minimum: true }),
  row({
    candidate_id: MARIA,
    full_name: "Maria Ivanova",
    position: 2,
    score: 42.5,
    meets_minimum: false,
  }),
];

const uploadResponse: CandidateUploadResponse = {
  candidate: {
    id: MARIA,
    full_name: "Maria Ivanova",
    email: null,
    source_filename: "cv.pdf",
    profile: {},
    created_at: "2026-08-27T09:00:00Z",
  },
  extraction: { engine: "tesseract", characters: 1840, confidence: 0.8 },
};

const rankResponse: RankResponse = {
  role_id: ROLE_ID,
  role_title: role.title,
  ruleset_id: "66666666-6666-6666-6666-666666666666",
  ruleset_version: "2026.08.1",
  engine: "rule_based",
  mode: "masked",
  ranked: [
    {
      position: 2,
      ranking_id: `ranking-${MARIA}`,
      candidate_id: MARIA,
      full_name: "Maria Ivanova",
      score: 42.5,
      meets_minimum: false,
      factors: [
        {
          name: "required_skills",
          weight: 3,
          subscore: 0.5,
          contribution: 21.2,
          matched: ["python"],
          missing: ["docker"],
          detail: "",
        },
      ],
    },
  ],
};

function pdf(name = "cv.pdf", size = 2048): File {
  const file = new File(["%PDF-1.7 ..."], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

/** Stands in for the candidate page, so the route params can be asserted. */
function CandidateStub() {
  const { roleId, candidateId } = useParams();
  return <div data-testid="candidate-page">{`${roleId}|${candidateId}`}</div>;
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={[`/roles/${ROLE_ID}`]}>
      <Routes>
        <Route path="/roles/:roleId" element={<PositionDetailPage />} />
        <Route path="/roles/:roleId/candidates/:candidateId" element={<CandidateStub />} />
      </Routes>
    </MemoryRouter>,
  );
  return {
    get input() {
      return screen.getByLabelText(/Drop a CV here or click/) as HTMLInputElement;
    },
  };
}

afterEach(() => vi.restoreAllMocks());

describe("the ranking", () => {
  it("lists every candidate with rank, name and score", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("№1")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Ivan Petrov")).toBeInTheDocument();
    expect(within(rows[0]).getByText("90.0")).toBeInTheDocument();
    expect(within(rows[1]).getByText("№2")).toBeInTheDocument();
    expect(within(rows[1]).getByText("42.5")).toBeInTheDocument();
  });

  it("badges only the candidates that meet the minimum", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();
    const rows = await screen.findAllByRole("listitem");

    expect(within(rows[0]).getByText("Meets minimum")).toBeInTheDocument();
    // No opposite label: a low score is not a refusal.
    expect(within(rows[1]).queryByText(/minimum/i)).not.toBeInTheDocument();
  });

  it("keeps the AI Act notice on the screen", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();

    expect(await screen.findByText(/AI-assisted/)).toHaveTextContent(
      /The recruiter makes the decision/,
    );
  });

  it("says so when nobody is ranked yet", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list([]));

    renderPage();

    expect(await screen.findByText(/No candidates ranked for this role yet/)).toBeInTheDocument();
  });

  it("colours a decided candidate and leaves the undecided plain", async () => {
    const decided = [
      row({ candidate_id: IVAN, full_name: "Ivan Petrov", position: 1, outcome: "advanced" }),
      row({ candidate_id: MARIA, full_name: "Maria Ivanova", position: 2, outcome: "rejected" }),
      row({ candidate_id: "c3", full_name: "Petya Hristova", position: 3, outcome: "pending" }),
      row({ candidate_id: "c4", full_name: "Elena Todorova", position: 4, outcome: "on_hold" }),
    ];
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(decided));

    renderPage();

    // The colour reports a recorded human decision, so it also says so in words.
    expect(await screen.findByText("Ivan Petrov")).toHaveClass("advanced");
    expect(screen.getByText("Ivan Petrov")).toHaveAttribute("title", "Advanced");
    expect(screen.getByText("Maria Ivanova")).toHaveClass("rejected");
    expect(screen.getByText("Maria Ivanova")).toHaveAttribute("title", "Rejected");

    // Undecided candidates carry no colour — the ranking judges no one by score.
    expect(screen.getByText("Petya Hristova").className).toBe("");
    expect(screen.getByText("Elena Todorova").className).toBe("");
  });

  it("keeps the summary area empty until a CV is uploaded", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();
    await screen.findByText("Ivan Petrov");

    expect(screen.queryByText("Required skills")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /full explanation/ })).not.toBeInTheDocument();
  });
});

describe("opening a candidate", () => {
  it("navigates with the role and candidate ids in the route", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /Ivan Petrov/ }));

    expect(await screen.findByTestId("candidate-page")).toHaveTextContent(`${ROLE_ID}|${IVAN}`);
  });
});

describe("uploading", () => {
  it("scores the new CV and reloads the ranking with it", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    const listRankings = vi
      .spyOn(api, "listRankings")
      .mockResolvedValueOnce(list([twoRows[0]]))
      .mockResolvedValue(list(twoRows));
    const upload = vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    const rank = vi.spyOn(api, "rank").mockResolvedValue(rankResponse);

    const page = renderPage();
    await screen.findByText("Ivan Petrov");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);

    await userEvent.upload(page.input, pdf());

    // Scoped to the list: the name also shows in the upload confirmation.
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(within(screen.getAllByRole("listitem")[1]).getByText("Maria Ivanova")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(1);
    // Only the new CV is scored, not the whole candidate set.
    expect(rank).toHaveBeenCalledWith(ROLE_ID, { candidateIds: [MARIA] });
    await waitFor(() => expect(listRankings).toHaveBeenCalledTimes(2));
  });

  it("records no decision while scoring", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    const rank = vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const putDecision = vi.spyOn(api, "putDecision");

    const page = renderPage();
    await screen.findByText("Ivan Petrov");
    await userEvent.upload(page.input, pdf());

    await waitFor(() => expect(rank).toHaveBeenCalled());
    expect(putDecision).not.toHaveBeenCalled();
  });

  it("does not send a file of an unaccepted type", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));
    const upload = vi.spyOn(api, "uploadCandidate");

    renderPage();
    const label = await screen.findByText(/Drop a CV here or click/);

    fireEvent.drop(label.closest(".dropzone") as HTMLElement, {
      dataTransfer: { files: [new File(["x"], "cv.docx", { type: "application/msword" })] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(/Only PDF and TXT/);
    expect(upload).not.toHaveBeenCalled();
  });

  it("tells uploaded-but-unscored apart from never accepted", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockRejectedValue(new ApiError(409, "No active ruleset."));

    const page = renderPage();
    await screen.findByText("Ivan Petrov");
    await userEvent.upload(page.input, pdf());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /The CV was uploaded, but scoring failed: No active ruleset./,
    );
  });
});

describe("the summary under the upload", () => {
  async function upload() {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);

    const page = renderPage();
    await screen.findByText("Ivan Petrov");
    await userEvent.upload(page.input, pdf());
    return screen.findByRole("link", { name: /full explanation/ });
  }

  it("shows the name, score and factors of the CV just added", async () => {
    await upload();
    const summary = document.querySelector(".upload-summary") as HTMLElement;

    expect(within(summary).getByText("Maria Ivanova")).toBeInTheDocument();
    expect(within(summary).getByText("42.5")).toBeInTheDocument();
    expect(within(summary).getByText("Required skills")).toBeInTheDocument();
    expect(within(summary).getByText("50%")).toBeInTheDocument();
  });

  it("marks covered skills green and missing ones red", async () => {
    await upload();
    const summary = document.querySelector(".upload-summary") as HTMLElement;

    expect(within(summary).getByText("python")).toHaveClass("chip", "matched");
    expect(within(summary).getByText("docker")).toHaveClass("chip", "missing");
  });

  it("links to the candidate page for the full explanation", async () => {
    const link = await upload();

    expect(link).toHaveAttribute("href", `/roles/${ROLE_ID}/candidates/${MARIA}`);
  });

  it("does not badge a candidate who misses the minimum", async () => {
    await upload();
    const summary = document.querySelector(".upload-summary") as HTMLElement;

    // No opposite label: the summary informs, it does not turn anyone down.
    expect(within(summary).queryByText(/minimum/i)).not.toBeInTheDocument();
  });
});

describe("the ranking sidebar", () => {
  it("has no control that hides it", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();
    await screen.findByText("Ivan Petrov");

    const sidebar = document.querySelector(".ranking-sidebar") as HTMLElement;
    expect(sidebar).toBeInTheDocument();
    // Every button inside the sidebar is a candidate row, nothing that closes it.
    const buttons = within(sidebar).getAllByRole("button");
    expect(buttons).toHaveLength(twoRows.length);
    expect(
      within(sidebar).queryByRole("button", { name: /close|collapse|hide/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps the AI Act notice inside the always-visible sidebar", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();
    await screen.findByText("Ivan Petrov");

    const sidebar = document.querySelector(".ranking-sidebar") as HTMLElement;
    expect(within(sidebar).getByText(/AI-assisted/)).toHaveTextContent(
      /The recruiter makes the decision/,
    );
  });
});

describe("the ruleset the ranking is read under", () => {
  it("states the version when the role has only one", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows));

    renderPage();

    expect(await screen.findByText("Ruleset 2026.08.1")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("offers a choice when the role was ranked under several", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    const listRankings = vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows, [V1, V0]));

    renderPage();
    await userEvent.selectOptions(await screen.findByRole("combobox"), "2026.07.1");

    // The older version is read from the backend, not filtered in the browser.
    await waitFor(() =>
      expect(listRankings).toHaveBeenLastCalledWith(ROLE_ID, { ruleset_version: "2026.07.1" }),
    );
  });

  it("returns to the default after an upload, so the new candidate is visible", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    const listRankings = vi.spyOn(api, "listRankings").mockResolvedValue(list(twoRows, [V1, V0]));
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);

    const page = renderPage();
    await userEvent.selectOptions(await screen.findByRole("combobox"), "2026.07.1");
    await waitFor(() =>
      expect(listRankings).toHaveBeenLastCalledWith(ROLE_ID, { ruleset_version: "2026.07.1" }),
    );

    await userEvent.upload(page.input, pdf());

    // Scoring runs under the active rules, so the view goes back to them.
    await waitFor(() => expect(listRankings).toHaveBeenLastCalledWith(ROLE_ID, {}));
  });
});

describe("a ranking longer than the page", () => {
  it("says when the list is cut short instead of quietly hiding people", async () => {
    vi.spyOn(api, "getRole").mockResolvedValue(role);
    vi.spyOn(api, "listRankings").mockResolvedValue({ ...list(twoRows), total: 240 });

    renderPage();

    expect(await screen.findByText(/Showing the first 2 of 240/)).toBeInTheDocument();
  });
});
