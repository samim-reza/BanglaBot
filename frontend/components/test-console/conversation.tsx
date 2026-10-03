"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

import type { Line } from "./types";

function TypingBubble() {
  return (
    <div className="flex justify-start" aria-label="Agent is typing">
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-secondary px-3.5 py-3">
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground motion-reduce:animate-none"
            style={{ animationDelay: `${dot * 150}ms` }}
            aria-hidden
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Chat-style transcript: the agent on the left, the caller (you) on the right,
 * system notes centred. Keeps itself scrolled to the newest line.
 */
export function Conversation({
  lines,
  typing,
  empty,
  className,
  label,
}: {
  lines: Line[];
  typing?: boolean;
  empty?: React.ReactNode;
  className?: string;
  label: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [lines.length, typing]);

  return (
    <div
      ref={scroller}
      role="log"
      aria-live="polite"
      aria-label={label}
      tabIndex={0}
      className={cn(
        "flex min-h-0 flex-col gap-2 overflow-y-auto rounded-md border border-border bg-surface p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      {lines.length === 0 && !typing ? (
        <div className="m-auto max-w-sm px-4 py-6 text-center text-sm text-muted-foreground">{empty}</div>
      ) : (
        lines.map((line) =>
          line.role === "system" ? (
            <p key={line.id} className="self-center rounded-full bg-secondary px-3 py-1 text-center text-xs text-muted-foreground">
              {line.text}
            </p>
          ) : (
            <div key={line.id} className={cn("flex", line.role === "agent" ? "justify-start" : "justify-end")}>
              <p
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                  line.role === "agent" ? "rounded-bl-sm border border-border bg-card text-card-foreground" : "rounded-br-sm bg-primary text-primary-foreground",
                )}
              >
                <span className="sr-only">{line.role === "agent" ? "Agent: " : "You: "}</span>
                {line.text}
              </p>
            </div>
          ),
        )
      )}
      {typing && <TypingBubble />}
    </div>
  );
}
