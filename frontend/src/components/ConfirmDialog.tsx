/**
 * A confirmation before something that cannot be undone.
 *
 * Focus starts on Cancel and stays inside the dialog — see `Modal`, which owns
 * those rules. The only way through is a deliberate click on the dangerous
 * button.
 */

import type { ReactNode } from "react";
import { Modal } from "./Modal";

interface Props {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <Modal title={title} busy={busy} onCancel={onCancel}>
      <div className="modal-body">{children}</div>
      <div className="modal-actions">
        <button type="button" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>
        <button type="button" className="danger" onClick={onConfirm} disabled={busy}>
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
