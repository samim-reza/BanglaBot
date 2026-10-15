"use client";

import { RotateCcw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Sticky bar while the draft differs from what is saved. */
export function SaveBar({ dirty, saving, onSave, onDiscard }: { dirty: boolean; saving: boolean; onSave: () => void; onDiscard: () => void }) {
  if (!dirty) return null;
  return (
    <div className="sticky bottom-3 z-30 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-3 shadow-lg">
      <span className="text-sm font-medium">Unsaved changes</span>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={onDiscard} disabled={saving}>
          <RotateCcw className="h-3.5 w-3.5" />
          Discard
        </Button>
        <Button size="sm" onClick={onSave} disabled={saving}>
          <Save className="h-3.5 w-3.5" />
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}
