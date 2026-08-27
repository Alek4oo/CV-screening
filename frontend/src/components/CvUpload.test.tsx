/**
 * Качване на CV от изгледа: какво стига до API-то, какво се отказва още тук и
 * какво вижда рекрутерът, докато файлът се обработва.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { MAX_UPLOAD_BYTES } from "../api/upload";
import type { CandidateUploadResponse, RankResponse } from "../api/types";
import { CvUpload } from "./CvUpload";

const ROLE_ID = "44444444-4444-4444-4444-444444444444";

function pdf(name = "cv.pdf", size = 2048): File {
  const file = new File(["%PDF-1.7 ..."], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

const uploadResponse: CandidateUploadResponse = {
  candidate: {
    id: "55555555-5555-5555-5555-555555555555",
    full_name: "Maria Ivanova",
    email: "maria@example.com",
    source_filename: "cv.pdf",
    profile: { skills: ["python"] },
    created_at: "2026-08-27T09:00:00Z",
  },
  extraction: { engine: "tesseract", characters: 1840, confidence: 0.8 },
};

const rankResponse: RankResponse = {
  role_id: ROLE_ID,
  role_title: "Backend Developer",
  ruleset_id: "66666666-6666-6666-6666-666666666666",
  ruleset_version: "2026.08.1",
  engine: "rule_based",
  mode: "masked",
  ranked: [
    {
      position: 1,
      ranking_id: "77777777-7777-7777-7777-777777777777",
      candidate_id: uploadResponse.candidate.id,
      full_name: "Maria Ivanova",
      score: 87.5,
      meets_minimum: true,
      factors: [],
    },
  ],
};

function renderUpload() {
  const onIngested = vi.fn();
  render(
    <MemoryRouter>
      <CvUpload roleId={ROLE_ID} roleTitle="Backend Developer" onIngested={onIngested} />
    </MemoryRouter>,
  );
  const input = screen.getByLabelText(/Drop the files here/) as HTMLInputElement;
  return { onIngested, input, dropzone: input.parentElement as HTMLElement };
}

afterEach(() => vi.restoreAllMocks());

describe("happy path", () => {
  it("uploads, scores and shows the score straight away", async () => {
    const upload = vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    const rank = vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const { onIngested, input } = renderUpload();

    await userEvent.upload(input, pdf());

    expect(await screen.findByText("87.5 pts")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(1);
    // Класира се само новото CV, не целият набор кандидати.
    expect(rank).toHaveBeenCalledWith(ROLE_ID, {
      candidateIds: [uploadResponse.candidate.id],
    });
    await waitFor(() => expect(onIngested).toHaveBeenCalled());
  });

  it("shows what the engine read", async () => {
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const { input } = renderUpload();

    await userEvent.upload(input, pdf());

    expect(await screen.findByText(/1840 characters/)).toBeInTheDocument();
    expect(screen.getByText(/tesseract/)).toBeInTheDocument();
    expect(screen.getByText(/Maria Ivanova/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /see the explanation/ })).toHaveAttribute(
      "href",
      `/rankings/${rankResponse.ranked[0].ranking_id}`,
    );
  });

  it("gives the new candidate a score but no decision", async () => {
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const putDecision = vi.spyOn(api, "putDecision");
    const { input } = renderUpload();

    await userEvent.upload(input, pdf());
    await screen.findByText("87.5 pts");

    expect(putDecision).not.toHaveBeenCalled();
  });

  it("warns on low parse confidence", async () => {
    vi.spyOn(api, "uploadCandidate").mockResolvedValue({
      ...uploadResponse,
      extraction: { engine: "tesseract", characters: 210, confidence: 0.2 },
    });
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const { input } = renderUpload();

    await userEvent.upload(input, pdf());

    expect(await screen.findByText(/parser recognised few sections/)).toBeInTheDocument();
  });

  it("handles several files and scores each on its own", async () => {
    const upload = vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const { input } = renderUpload();

    await userEvent.upload(input, [pdf("a.pdf"), pdf("b.pdf")]);

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
  });
});

describe("refusals before the network", () => {
  it("does not send a file of an unaccepted type", async () => {
    // Диалогът за избор филтрира по `accept`; през влачене такъв файл минава,
    // затова тестът върви по пътя, по който проблемът реално стига дотук.
    const upload = vi.spyOn(api, "uploadCandidate");
    const { dropzone } = renderUpload();

    fireEvent.drop(dropzone, {
      dataTransfer: { files: [new File(["x"], "cv.docx", { type: "application/msword" })] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(/Only PDF and TXT/);
    expect(upload).not.toHaveBeenCalled();
  });

  it("a dropped PDF takes the same path as a picked one", async () => {
    const upload = vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const { dropzone } = renderUpload();

    fireEvent.drop(dropzone, { dataTransfer: { files: [pdf()] } });

    expect(await screen.findByText("87.5 pts")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(1);
  });

  it("does not send a file over the limit", async () => {
    const upload = vi.spyOn(api, "uploadCandidate");
    const { input } = renderUpload();

    await userEvent.upload(input, pdf("huge.pdf", MAX_UPLOAD_BYTES + 1));

    expect(await screen.findByRole("alert")).toHaveTextContent(/over the 10 MB limit/);
    expect(upload).not.toHaveBeenCalled();
  });
});

describe("backend errors", () => {
  it("shows the read refusal exactly as it came", async () => {
    vi.spyOn(api, "uploadCandidate").mockRejectedValue(
      new ApiError(422, "No text was extracted from the document."),
    );
    const { onIngested, input } = renderUpload();

    await userEvent.upload(input, pdf());

    expect(await screen.findByRole("alert")).toHaveTextContent(/No text was extracted/);
    expect(onIngested).not.toHaveBeenCalled();
  });

  it("tells uploaded-but-unscored apart from never accepted", async () => {
    vi.spyOn(api, "uploadCandidate").mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockRejectedValue(
      new ApiError(409, "No active ruleset."),
    );
    const { input } = renderUpload();

    await userEvent.upload(input, pdf());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /The CV was uploaded, but scoring failed: No active ruleset./,
    );
  });

  it("one failed file does not stop the rest", async () => {
    vi.spyOn(api, "uploadCandidate")
      .mockRejectedValueOnce(new ApiError(422, "The document could not be read"))
      .mockResolvedValue(uploadResponse);
    vi.spyOn(api, "rank").mockResolvedValue(rankResponse);
    const { input } = renderUpload();

    await userEvent.upload(input, [pdf("bad.pdf"), pdf("good.pdf")]);

    expect(await screen.findByText("87.5 pts")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/could not be read/);
    expect(screen.getByText(/1 file was not accepted/)).toBeInTheDocument();
  });
});
