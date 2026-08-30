/**
 * The shell of the recruiter view.
 *
 * The avatar on the right is not decoration: behind it sits the "You are"
 * field. A decision needs a name — it goes into `Decision.decided_by` and into
 * the audit log — and the project has no authentication. Writing "system" in
 * the who-confirmed column would be a lie, so the person says who they are.
 * Tucked into the avatar, but one click away on every screen.
 */

import { useEffect, useRef, useState } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useRecruiter } from "./hooks";
import { PositionsPage } from "./pages/PositionsPage";
import { PositionDetailPage } from "./pages/PositionDetailPage";
import { RankingDetailPage } from "./pages/RankingDetailPage";

export default function App() {
  useScrollbarWidth();

  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          Sirma
        </Link>
        <div className="spacer" />
        <RecruiterAvatar />
      </header>

      <main>
        <Routes>
          <Route path="/" element={<PositionsPage />} />
          <Route path="/roles/:roleId" element={<PositionDetailPage />} />
          <Route
            path="/roles/:roleId/candidates/:candidateId"
            element={<RankingDetailPage />}
          />
          <Route path="/rankings/:rankingId" element={<RankingDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}

/**
 * Publishes the scrollbar width as `--scrollbar`.
 *
 * CSS can ask for `100vw`, which counts the scrollbar, but not for the width
 * actually visible. The position screen pulls its ranking rail out to the right
 * edge of the screen and needs the difference, or the page gains a horizontal
 * scrollbar exactly as wide as the vertical one.
 */
function useScrollbarWidth() {
  useEffect(() => {
    function measure() {
      const width = window.innerWidth - document.documentElement.clientWidth;
      document.documentElement.style.setProperty("--scrollbar", `${width}px`);
    }

    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
}

/** The recruiter's initials, and under them the field that fills them. */
function RecruiterAvatar() {
  const [recruiter, setRecruiter] = useRecruiter();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="avatar-menu" ref={containerRef}>
      <button
        type="button"
        className="avatar"
        aria-label="You are"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {initials(recruiter)}
      </button>

      {open && (
        <div className="avatar-popover">
          <label htmlFor="recruiter">You are</label>
          <input
            id="recruiter"
            value={recruiter}
            placeholder="name or email"
            onChange={(event) => setRecruiter(event.target.value)}
          />
          <span className="small muted">
            The name is recorded on decisions and in the audit log.
          </span>
        </div>
      )}
    </div>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
