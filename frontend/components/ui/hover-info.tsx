"use client";

import { ReactNode, useCallback, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * A hover tooltip that renders its panel in a portal on `document.body`, so it
 * escapes any `overflow`-clipping or stacking context of the table/card it lives
 * in. Positions itself above the trigger, flipping below when there isn't room,
 * and clamps to the viewport. Use for rich breakdowns that a title= can't show.
 */
export function HoverInfo({
  trigger,
  children,
  width = 288,
  className,
}: {
  trigger: ReactNode;
  children: ReactNode;
  width?: number;
  className?: string;
}) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; placement: "top" | "bottom" }>({
    top: 0,
    left: 0,
    placement: "top",
  });

  const place = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const spaceAbove = r.top;
    const placement: "top" | "bottom" = spaceAbove > 200 ? "top" : "bottom";
    // Right-align the panel to the trigger, then clamp inside the viewport.
    let left = r.right - width;
    left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
    const top = placement === "top" ? r.top - margin : r.bottom + margin;
    setPos({ top, left, placement });
  }, [width]);

  useLayoutEffect(() => {
    if (!open) return;
    place();
    const onScroll = () => place();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open, place]);

  return (
    <span
      ref={anchorRef}
      className="inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {trigger}
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <span
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              width,
              transform: pos.placement === "top" ? "translateY(-100%)" : undefined,
            }}
            className={`pointer-events-none z-[1000] block whitespace-normal rounded-md border bg-card p-3 text-left shadow-lg ${className ?? ""}`}
          >
            {children}
          </span>,
          document.body,
        )}
    </span>
  );
}
