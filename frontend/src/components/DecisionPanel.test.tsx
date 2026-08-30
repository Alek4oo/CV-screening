/**
 * Панелът за решение — тестовете пазят това, което PRD-то забранява да се
 * заобикаля: статус се сменя само от човек, само с обосновка и само нарочно.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Decision } from "../api/types";
import { DecisionPanel } from "./DecisionPanel";

const RANKING_ID = "11111111-1111-1111-1111-111111111111";

function decisionFrom(outcome: Decision["outcome"], rationale: string): Decision {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    ranking_id: RANKING_ID,
    ruleset_id: "33333333-3333-3333-3333-333333333333",
    outcome,
    decided_by: "recruiter",
    decided_at: "2026-08-27T09:00:00Z",
    rationale,
    created_at: "2026-08-27T09:00:00Z",
    updated_at: "2026-08-27T09:00:00Z",
  };
}

function renderPanel(overrides: Partial<Parameters<typeof DecisionPanel>[0]> = {}) {
  const onRecorded = vi.fn();
  render(
    <DecisionPanel
      rankingId={RANKING_ID}
      decision={null}
      recruiter="recruiter"
      onRecorded={onRecorded}
      {...overrides}
    />,
  );
  return { onRecorded };
}

const submitButton = () => screen.getByRole("button", { name: /Save decision/ });

afterEach(() => vi.restoreAllMocks());

describe("guards before saving", () => {
  it("blocks saving with no status picked", () => {
    renderPanel();
    expect(submitButton()).toBeDisabled();
  });

  it("blocks saving with no rationale", async () => {
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /Rejected/ }));
    expect(submitButton()).toBeDisabled();
  });

  it("blocks saving with no recruiter name", async () => {
    renderPanel({ recruiter: "   " });
    await userEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    await userEvent.type(screen.getByLabelText(/Rationale/), "strong profile");

    expect(submitButton()).toBeDisabled();
    expect(screen.getByText(/Enter your name/)).toBeInTheDocument();
  });

  it("unlocks saving only with person, status and rationale", async () => {
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    await userEvent.type(screen.getByLabelText(/Rationale/), "strong profile");

    expect(submitButton()).toBeEnabled();
  });

  it("preselects no status", () => {
    renderPanel();
    for (const label of ["For review", "Advanced", "Rejected", "On hold"]) {
      expect(screen.getByRole("button", { name: new RegExp(label) })).toHaveAttribute(
        "aria-pressed",
        "false",
      );
    }
  });
});

describe("saving", () => {
  it("sends outcome, person and rationale to the API", async () => {
    const put = vi
      .spyOn(api, "putDecision")
      .mockResolvedValue(decisionFrom("rejected", "short of the required years"));
    const { onRecorded } = renderPanel({ recruiter: "  ana@sirma.bg  " });

    await userEvent.click(screen.getByRole("button", { name: /Rejected/ }));
    await userEvent.type(screen.getByLabelText(/Rationale/), "short of the required years");
    await userEvent.click(submitButton());

    expect(put).toHaveBeenCalledWith(RANKING_ID, {
      outcome: "rejected",
      decided_by: "ana@sirma.bg",
      rationale: "short of the required years",
    });
    expect(onRecorded).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/written to the audit log/)).toBeInTheDocument();
  });

  it("surfaces the backend refusal instead of hiding it", async () => {
    vi.spyOn(api, "putDecision").mockRejectedValue(
      new (class extends Error {
        status = 422;
      })("rationale: The field cannot be only whitespace."),
    );
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /Rejected/ }));
    await userEvent.type(screen.getByLabelText(/Rationale/), "x");
    await userEvent.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot be only whitespace/);
  });

  it("shows the current decision and its rationale", () => {
    renderPanel({ decision: decisionFrom("on_hold", "waiting on a reference") });

    // Текстът се среща и като бутон за избор — тук ни трябва значката за статус.
    expect(screen.getByText("On hold", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.getByText("waiting on a reference")).toBeInTheDocument();
  });

  it("says no one has decided yet when there is no decision", () => {
    renderPanel();
    expect(screen.getByText(/No one has decided/)).toBeInTheDocument();
  });
});
