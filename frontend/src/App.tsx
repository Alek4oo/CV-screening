/**
 * Каркасът на изгледа за рекрутер.
 *
 * Полето „Вие сте" в хедъра не е козметика: решението изисква име, което влиза
 * в `Decision.decided_by` и в одитния лог. Проектът няма аутентикация, а да се
 * запише „system" в графата „кой потвърди" би било невярно — затова човекът се
 * представя сам и това е видимо на всеки екран.
 */

import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useRecruiter } from "./hooks";
import { RolesPage } from "./pages/RolesPage";
import { RoleRankingPage } from "./pages/RoleRankingPage";
import { RankingDetailPage } from "./pages/RankingDetailPage";

export default function App() {
  const [recruiter, setRecruiter] = useRecruiter();

  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          Candidate Ranking
          <span>The human decides · EU AI Act, Annex III §4</span>
        </Link>
        <div className="spacer" />
        <div className="recruiter-field">
          <label htmlFor="recruiter" style={{ margin: 0 }}>
            You are
          </label>
          <input
            id="recruiter"
            value={recruiter}
            placeholder="name or email"
            onChange={(event) => setRecruiter(event.target.value)}
          />
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<RolesPage />} />
          <Route path="/roles/:roleId" element={<RoleRankingPage />} />
          <Route path="/rankings/:rankingId" element={<RankingDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
