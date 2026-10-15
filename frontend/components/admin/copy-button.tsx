"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Copies `value` to the clipboard; shows a tick for a moment. */
export function CopyButton({ value, label = "Copy", title }: { value: string; label?: string; title?: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      window.prompt("Copy this:", value);
    }
  };
  return (
    <Button type="button" variant="outline" size="sm" onClick={() => void copy()} title={title} aria-live="polite">
      {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {done ? "Copied" : label}
    </Button>
  );
}
