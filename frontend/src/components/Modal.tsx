/**
 * The shell both dialogs sit in: backdrop, panel, and the focus rules.
 *
 * A modal that lets Tab wander into the page behind it is not modal — a screen
 * reader or a keyboard user ends up operating controls they cannot see, with
 * the dialog still open on top. So focus starts inside, cycles inside, and
 * returns to whatever opened the dialog when it closes.
 *
 * Escape and a click on the backdrop cancel; both are refused while `busy`, so
 * a dialog cannot be dismissed out from under a request that is still running.
 */

import { useEffect, useRef, type ReactNode } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

interface Props {
  /** Names the dialog for assistive technology and titles the panel. */
  title: string;
  children: ReactNode;
  busy?: boolean;
  onCancel: () => void;
}

export function Modal({ title, children, busy = false, onCancel }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;

    // Първият фокусируем елемент е „Откажи"/затварящото действие: диалог, който
    // изтрива при случаен Enter, не е потвърждение.
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel)?.focus();

    return () => opener?.focus?.();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (!busy) onCancel();
        return;
      }

      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;

      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (item) => item.offsetParent !== null || item === document.activeElement,
      );
      if (!items.length) {
        event.preventDefault();
        return;
      }

      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;

      // Табът се завърта в рамките на панела вместо да излезе зад него.
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [busy, onCancel]);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={panelRef}
        tabIndex={-1}
      >
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}
