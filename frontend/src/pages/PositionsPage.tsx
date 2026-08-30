/**
 * The positions, and the way into each one.
 *
 * A card carries the count of candidates ranked for that position. The count
 * costs one request per position: no endpoint returns it for all of them at
 * once, and the ranking is the only place it lives. The requests run in
 * parallel, and one failing does not break the cards — that count stays "—".
 *
 * Deleting goes through a confirmation, because it cannot be undone. The
 * backend protects the ranked: a position with rankings comes back as 409 with
 * an explanation to close it instead. That message is shown as it came, rather
 * than hidden behind "something went wrong".
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Role } from "../api/types";
import { useAsync } from "../hooks";
import { Loading, Notice } from "../components/common";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { NewPositionDialog } from "../components/NewPositionDialog";

export function PositionsPage() {
  const navigate = useNavigate();
  const roles = useAsync(() => api.listRoles(), []);
  const [counts, setCounts] = useState<Record<string, number | null>>({});
  const [pendingDelete, setPendingDelete] = useState<Role | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const list = roles.data;

  useEffect(() => {
    if (!list) return;
    let current = true;

    void Promise.all(
      list.map(async (role) => {
        try {
          return [role.id, await api.countCandidates(role.id)] as const;
        } catch {
          // Класацията на една позиция може да откаже, без това да чупи екрана.
          return [role.id, null] as const;
        }
      }),
    ).then((pairs) => {
      if (current) setCounts(Object.fromEntries(pairs));
    });

    return () => {
      current = false;
    };
  }, [list]);

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteRole(pendingDelete.id);
      setPendingDelete(null);
      roles.reload();
    } catch (cause) {
      setDeleteError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, roles]);

  return (
    <>
      <div className="page-head">
        <h1>Positions</h1>
        <div className="spacer" style={{ flex: 1 }} />
        <button type="button" className="primary" onClick={() => setCreating(true)}>
          New position
        </button>
      </div>

      {roles.error && <Notice kind="error">{roles.error}</Notice>}
      {deleteError && !pendingDelete && <Notice kind="error">{deleteError}</Notice>}
      {roles.loading && !list && <Loading what="positions" />}

      {list && !list.length && (
        <div className="card">
          <div className="empty">
            No positions yet.
            <br />
            <span className="small">Create the first one with “New position”.</span>
          </div>
        </div>
      )}

      <div className="position-grid">
        {list?.map((role) => (
          <PositionCard
            key={role.id}
            role={role}
            count={counts[role.id]}
            onDelete={() => {
              setDeleteError(null);
              setPendingDelete(role);
            }}
          />
        ))}
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Delete position"
          confirmLabel="Delete"
          busy={deleting}
          onConfirm={confirmDelete}
          onCancel={() => {
            setPendingDelete(null);
            setDeleteError(null);
          }}
        >
          <p>
            The position <strong>{pendingDelete.title}</strong> will be deleted. This cannot be
            undone.
          </p>
          {deleteError && <Notice kind="error">{deleteError}</Notice>}
        </ConfirmDialog>
      )}

      {creating && (
        <NewPositionDialog
          onCancel={() => setCreating(false)}
          onCreated={(role) => {
            setCreating(false);
            navigate(`/roles/${role.id}`);
          }}
        />
      )}
    </>
  );
}

interface CardProps {
  role: Role;
  /** undefined = still counting, null = the count failed. */
  count: number | null | undefined;
  onDelete: () => void;
}

/**
 * Заглавието е истинска връзка, а не div с role="button".
 *
 * Два интерактивни елемента един в друг са невалиден ARIA и екранните четци ги
 * четат объркано, а кошчето стои точно вътре в картичката. Затова връзката се
 * разпъва върху цялата картичка през ::after, а кошчето се вдига над нея — така
 * целият правоъгълник е кликаем, но всеки от двата елемента си остава сам за
 * себе си. Като връзка заглавието получава и среден бутон, и „отвори в нов таб",
 * които onClick върху div поглъщаше.
 */
function PositionCard({ role, count, onDelete }: CardProps) {
  return (
    <div className="card position-card">
      <button
        type="button"
        className="icon-button"
        aria-label={`Delete position ${role.title}`}
        onClick={onDelete}
      >
        <TrashIcon />
      </button>

      <h3>
        <Link to={`/roles/${role.id}`}>{role.title}</Link>
      </h3>
      <div className="small muted">
        {count === undefined ? "…" : count === null ? "—" : candidateCount(count)}
      </div>
    </div>
  );
}

function candidateCount(count: number): string {
  return count === 1 ? "1 candidate" : `${count} candidates`;
}

function TrashIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 7h16" />
      <path d="M10 11v6M14 11v6" />
      <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
      <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  );
}
