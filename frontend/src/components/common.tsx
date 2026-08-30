/** Малките парчета, които се повтарят из изгледите. */

import type { ReactNode } from "react";
import type { DecisionOutcome } from "../api/types";
import { OUTCOME_LABELS } from "../api/labels";

export function OutcomeBadge({ outcome }: { outcome: DecisionOutcome }) {
  return <span className={`badge ${outcome}`}>{OUTCOME_LABELS[outcome]}</span>;
}

/**
 * Флагът за минимума — умишлено не изглежда като отказ.
 *
 * Непокритият минимум е информация за рекрутера. Червено „REJECTED" би свършило
 * работата на автоматичното отхвърляне, само че с цвят вместо с код.
 */
export function MinimumBadge({ meets }: { meets: boolean }) {
  return meets ? (
    <span className="badge ok">Meets minimum</span>
  ) : (
    <span className="badge warn">Minimum not met</span>
  );
}

export function Chips({ items, kind }: { items: string[]; kind?: "matched" | "missing" }) {
  if (!items.length) return <span className="muted small">—</span>;
  return (
    <div className="chips">
      {items.map((item) => (
        <span key={item} className={`chip ${kind ?? ""}`}>
          {item}
        </span>
      ))}
    </div>
  );
}

export function Notice({
  kind = "info",
  children,
}: {
  kind?: "info" | "warn" | "error";
  children: ReactNode;
}) {
  return (
    <div className={`notice ${kind}`} role={kind === "error" ? "alert" : undefined}>
      {children}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <div className="empty">Loading {what}…</div>;
}
