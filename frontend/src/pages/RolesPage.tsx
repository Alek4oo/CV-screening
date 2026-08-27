/** Изборът на роля — входът към класацията. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ROLE_STATUS_LABELS } from "../api/labels";
import type { RoleStatus } from "../api/types";
import { useAsync } from "../hooks";
import { Loading, Notice } from "../components/common";

const STATUS_TABS: { value: RoleStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "draft", label: "Drafts" },
  { value: "closed", label: "Closed" },
];

export function RolesPage() {
  const [status, setStatus] = useState<RoleStatus | "">("open");
  const roles = useAsync(() => api.listRoles(status || undefined), [status]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Roles</h1>
          <div className="subtitle">Pick a role to see the candidates ranked for it.</div>
        </div>
      </div>

      <div className="status-bar" role="group" aria-label="Filter by role status">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value || "all"}
            type="button"
            className="status-chip"
            aria-pressed={status === tab.value}
            onClick={() => setStatus(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {roles.error && <Notice kind="error">{roles.error}</Notice>}
      {roles.loading && !roles.data && <Loading what="roles" />}

      {roles.data && !roles.data.length && (
        <div className="card">
          <div className="empty">
            No roles with this status.
            <br />
            <span className="small">
              Create one via <code>POST /roles</code>, or load the seed set:{" "}
              <code>python -m app.seed</code>.
            </span>
          </div>
        </div>
      )}

      <div className="role-list">
        {roles.data?.map((role) => (
          <Link key={role.id} to={`/roles/${role.id}`} className="card role-card">
            <h3>{role.title}</h3>
            <div className="small muted" style={{ marginBottom: 8 }}>
              {ROLE_STATUS_LABELS[role.status]}
              {role.external_ref ? ` · ${role.external_ref}` : ""}
            </div>
            {role.description && <p className="small muted">{role.description}</p>}
            <div className="chips">
              {(role.requirements.required_skills ?? []).slice(0, 5).map((skill) => {
                const name = typeof skill === "string" ? skill : skill.name;
                return (
                  <span key={name} className="chip">
                    {name}
                  </span>
                );
              })}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
