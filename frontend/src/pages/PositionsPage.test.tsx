/**
 * The positions screen: what a card shows, and what has to happen before a
 * position disappears.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { Role } from "../api/types";
import { PositionsPage } from "./PositionsPage";

function role(id: string, title: string): Role {
  return {
    id,
    external_ref: null,
    title,
    description: null,
    requirements: {},
    status: "open",
    created_at: "2026-08-27T09:00:00Z",
    updated_at: "2026-08-27T09:00:00Z",
  };
}

const backend = role("11111111-1111-1111-1111-111111111111", "Backend Developer");
const analyst = role("22222222-2222-2222-2222-222222222222", "Analyst");

function renderPage() {
  render(
    <MemoryRouter>
      <PositionsPage />
    </MemoryRouter>,
  );
}

/** The card grid only — the title also appears in the delete dialog. */
function grid(): HTMLElement {
  return document.querySelector(".position-grid") as HTMLElement;
}

afterEach(() => vi.restoreAllMocks());

describe("the list", () => {
  it("shows a title and a candidate count on every position", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend, analyst]);
    vi.spyOn(api, "countCandidates").mockImplementation(async (roleId) =>
      roleId === backend.id ? 6 : 1,
    );

    renderPage();

    expect(await screen.findByText("Backend Developer")).toBeInTheDocument();
    expect(await screen.findByText("6 candidates")).toBeInTheDocument();
    // The one count that needs the singular.
    expect(await screen.findByText("1 candidate")).toBeInTheDocument();
  });

  it("survives a count failing for one position", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockRejectedValue(new ApiError(500, "boom"));

    renderPage();

    expect(await screen.findByText("Backend Developer")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("—")).toBeInTheDocument());
  });
});

describe("opening a position", () => {
  it("uses a real link, so the card survives middle-click and new-tab", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(3);

    renderPage();

    expect(await screen.findByRole("link", { name: "Backend Developer" })).toHaveAttribute(
      "href",
      `/roles/${backend.id}`,
    );
  });

  it("puts the delete button beside the link, not inside it", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(3);

    renderPage();

    const link = await screen.findByRole("link", { name: "Backend Developer" });
    const trash = screen.getByRole("button", { name: /Delete position/ });
    // Nested interactives are invalid ARIA; neither may contain the other.
    expect(link.contains(trash)).toBe(false);
    expect(trash.contains(link)).toBe(false);
  });
});

describe("the confirm dialog", () => {
  async function openDialog() {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(0);
    vi.spyOn(api, "deleteRole").mockResolvedValue();

    renderPage();
    await screen.findByRole("link", { name: "Backend Developer" });
    await userEvent.click(screen.getByRole("button", { name: /Delete position/ }));
    return screen.findByRole("dialog");
  }

  it("opens with focus on Cancel, not on the destructive button", async () => {
    await openDialog();

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("keeps Tab inside the dialog", async () => {
    const dialog = await openDialog();

    // Tab through more stops than the dialog holds; focus must never escape it.
    for (let step = 0; step < 5; step += 1) {
      await userEvent.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });

  it("returns focus to what opened it", async () => {
    await openDialog();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Delete position/ })).toHaveFocus(),
    );
  });
});

describe("deleting", () => {
  it("does not delete before it is confirmed", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(0);
    const remove = vi.spyOn(api, "deleteRole").mockResolvedValue();

    renderPage();
    const card = await screen.findByText("Backend Developer");
    await userEvent.click(
      within(card.closest(".position-card") as HTMLElement).getByRole("button", {
        name: /Delete position/,
      }),
    );

    expect(await screen.findByRole("dialog")).toHaveTextContent(/cannot be undone/);
    expect(remove).not.toHaveBeenCalled();
  });

  it("cancelling closes the dialog and keeps the position", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(0);
    const remove = vi.spyOn(api, "deleteRole").mockResolvedValue();

    renderPage();
    await screen.findByText("Backend Developer");
    await userEvent.click(screen.getByRole("button", { name: /Delete position/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(remove).not.toHaveBeenCalled();
    expect(within(grid()).getByText("Backend Developer")).toBeInTheDocument();
  });

  it("confirming deletes and reloads the list", async () => {
    const list = vi
      .spyOn(api, "listRoles")
      .mockResolvedValueOnce([backend])
      .mockResolvedValue([]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(0);
    const remove = vi.spyOn(api, "deleteRole").mockResolvedValue();

    renderPage();
    await screen.findByText("Backend Developer");
    await userEvent.click(screen.getByRole("button", { name: /Delete position/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith(backend.id));
    expect(list).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/No positions yet/)).toBeInTheDocument();
  });

  it("shows the backend refusal when the position has ranked candidates", async () => {
    vi.spyOn(api, "listRoles").mockResolvedValue([backend]);
    vi.spyOn(api, "countCandidates").mockResolvedValue(6);
    vi.spyOn(api, "deleteRole").mockRejectedValue(
      new ApiError(409, "The role has 6 rankings and is not deleted. Close it with status=closed."),
    );

    renderPage();
    await screen.findByText("Backend Developer");
    await userEvent.click(screen.getByRole("button", { name: /Delete position/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    // The message stays in the dialog — nothing was deleted, and why is visible.
    expect(await screen.findByRole("alert")).toHaveTextContent(/6 rankings/);
    expect(within(grid()).getByText("Backend Developer")).toBeInTheDocument();
  });
});
