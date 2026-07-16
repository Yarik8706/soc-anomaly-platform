"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

export function Modal({
  open,
  title,
  description,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="modal"
      onCancel={onClose}
      onClose={onClose}
      aria-labelledby="modal-title"
    >
      <div className="modal-header">
        <div>
          <h2 id="modal-title">{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Закрыть">
          <X />
        </button>
      </div>
      {children}
    </dialog>
  );
}
