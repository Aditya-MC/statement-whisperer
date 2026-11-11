import { useEffect, useId, useRef } from "react";

/**
 * Pixel-panel modal: dimmed backdrop, pops in, Escape or a backdrop click closes it.
 * Focus moves to the first button (or `initialFocus`) when it opens.
 */
export function Modal({ title, onClose, children, initialFocus, maxWidth = "max-w-md" }) {
  const titleId = useId();
  const panelRef = useRef(null);

  useEffect(() => {
    const target = initialFocus?.current ?? panelRef.current?.querySelector("button, input, select");
    target?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, initialFocus]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-[15vh] backdrop-blur-[2px]"
      onMouseDown={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onMouseDown={(e) => e.stopPropagation()}
        className={`pop-in flex w-full ${maxWidth} flex-col gap-4 border-2 border-glass-border bg-surface-solid p-6 shadow-[6px_6px_0_0_var(--axis)]`}
      >
        <h2 id={titleId} className="font-pixel text-lg leading-tight uppercase">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}

/** A big, keyboard-friendly choice button used inside modals. */
function Choice({ label, detail, onClick, autoFocusRef }) {
  return (
    <button
      ref={autoFocusRef}
      type="button"
      onClick={onClick}
      className="group flex w-full flex-col gap-1 border-2 border-line bg-surface px-4 py-3 text-left transition hover:-translate-x-px hover:-translate-y-px hover:border-ink hover:shadow-[4px_4px_0_0_var(--axis)] focus-visible:border-ink focus-visible:outline-none active:translate-x-0.5 active:translate-y-0.5 active:shadow-none"
    >
      <span className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide">
        <span aria-hidden="true" className="opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
          ▶
        </span>
        {label}
      </span>
      <span className="text-xs text-ink-2">{detail}</span>
    </button>
  );
}

/**
 * Asked after picking a category for a transaction: change only this row, or apply to every
 * transaction from the same merchant (and remember it for future imports).
 */
export function ApplyScopeDialog({ merchant, categoryName, onChoose, onClose }) {
  const firstRef = useRef(null);
  return (
    <Modal title="Apply category" onClose={onClose} initialFocus={firstRef}>
      <p className="text-sm text-ink-2">
        Set <span className="font-bold text-ink">{merchant}</span> to{" "}
        <span className="font-bold text-ink">{categoryName}</span>?
      </p>
      <div className="flex flex-col gap-2">
        <Choice
          autoFocusRef={firstRef}
          label="Only this transaction"
          detail="Changes just this one row. Nothing is remembered."
          onClick={() => onChoose(false)}
        />
        <Choice
          label={`Apply to all ${merchant}`}
          detail="Updates every other transaction from this merchant and remembers it for future imports. Rows you set by hand stay as they are."
          onClick={() => onChoose(true)}
        />
      </div>
      <div className="flex justify-end">
        <button type="button" className="btn-ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
    </Modal>
  );
}

/** Yes/no confirmation in the app's style (instead of the browser's confirm popup). */
export function ConfirmDialog({ title, children, confirmLabel = "Confirm", busy, onConfirm, onClose }) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="text-sm text-ink-2">{children}</div>
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn-primary !border-critical !bg-critical !text-surface-solid"
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
