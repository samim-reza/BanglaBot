"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatApiError } from "@/services/api";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A modal surface: a centred dialog or a right-hand drawer.
 *
 * Rendered in a portal on `document.body`, it traps Tab inside the panel,
 * closes on Escape or a backdrop click (unless `busy`), locks page scroll and
 * hands focus back to whatever opened it. It sits above the console header
 * (z-40) but below the toast stack (z-50), so save errors stay visible.
 */
export function Overlay({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  variant = "modal",
  size = "md",
  busy = false,
  initialFocus,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  variant?: "modal" | "drawer";
  size?: "sm" | "md" | "lg";
  busy?: boolean;
  /** CSS selector inside the panel to focus first (defaults to the first field). */
  initialFocus?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const busyRef = useRef(busy);
  const closeRef = useRef(onClose);

  useEffect(() => {
    busyRef.current = busy;
    closeRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    const panel = panelRef.current;
    const focusFirst = () => {
      if (!panel) return;
      const preferred = initialFocus ? panel.querySelector<HTMLElement>(initialFocus) : null;
      const body = panel.querySelector<HTMLElement>("[data-overlay-body]");
      const first = preferred ?? body?.querySelector<HTMLElement>(FOCUSABLE) ?? panel.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? panel).focus();
    };
    const frame = window.requestAnimationFrame(focusFirst);

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!busyRef.current) {
          event.stopPropagation();
          closeRef.current();
        }
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null);
      if (!items.length) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [open, initialFocus]);

  if (!open || typeof document === "undefined") return null;

  const drawer = variant === "drawer";
  const width = size === "sm" ? "max-w-md" : size === "lg" ? "max-w-3xl" : drawer ? "max-w-xl" : "max-w-lg";

  return createPortal(
    <div className={cn("fixed inset-0 z-[45] flex", drawer ? "justify-end" : "items-end justify-center p-0 sm:items-center sm:p-4")}>
      <div className="absolute inset-0 bg-black/40 dark:bg-black/60" aria-hidden="true" onClick={() => !busy && onClose()} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "relative flex w-full flex-col bg-card text-card-foreground shadow-xl outline-none",
          width,
          drawer
            ? "h-full border-l border-border"
            : "max-h-[92vh] rounded-t-xl border border-border sm:max-h-[88vh] sm:rounded-xl",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-lg font-semibold leading-snug">
              {title}
            </h2>
            {description && (
              <div id={descriptionId} className="mt-1 text-sm text-muted-foreground">
                {description}
              </div>
            )}
          </div>
          <Button variant="ghost" size="icon" className="-mr-2 h-9 w-9 shrink-0" onClick={onClose} disabled={busy} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div data-overlay-body className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {children}
        </div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

/** Inline error for a dialog (the shared ApiError has a page-level title). */
export function DialogError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-foreground">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

/**
 * Confirmation step for consequential actions. `onConfirm` may reject; the
 * error is shown inside the dialog and it stays open. With `confirmText`, the
 * button only enables once the admin has typed that exact text.
 */
export function ConfirmDialog({
  open,
  onClose,
  title,
  children,
  confirmLabel,
  busyLabel,
  tone = "default",
  confirmText,
  confirmTextLabel,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  busyLabel?: string;
  tone?: "default" | "danger";
  confirmText?: string;
  confirmTextLabel?: React.ReactNode;
  onConfirm: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const inputId = useId();

  useEffect(() => {
    if (open) {
      setBusy(false);
      setError(null);
      setTyped("");
    }
  }, [open]);

  const matches = !confirmText || typed.trim() === confirmText;

  const confirm = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!matches || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(formatApiError(err, "Something went wrong."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Overlay
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      busy={busy}
      initialFocus={confirmText ? "input" : "[data-confirm-cancel]"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy} data-confirm-cancel>
            Cancel
          </Button>
          <Button variant={tone === "danger" ? "destructive" : "default"} onClick={() => void confirm()} disabled={!matches || busy}>
            {busy ? busyLabel ?? "Working…" : confirmLabel}
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={confirm}>
        <div className="space-y-2 text-sm text-muted-foreground">{children}</div>
        {confirmText && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor={inputId} className="text-[13.5px] font-semibold text-muted-foreground">
              {confirmTextLabel ?? (
                <>
                  Type <span className="font-mono text-foreground">{confirmText}</span> to confirm
                </>
              )}
            </label>
            <Input
              id={inputId}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
            />
          </div>
        )}
        <DialogError message={error} />
      </form>
    </Overlay>
  );
}
