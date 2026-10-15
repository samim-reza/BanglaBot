"use client";

import { cn } from "@/lib/utils";

export type AccountTab = "overview" | "flow" | "providers";

export const ACCOUNT_TABS: { key: AccountTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "flow", label: "Call flow" },
  { key: "providers", label: "Providers" },
];

export function AccountTabs({ value, onChange }: { value: AccountTab; onChange: (tab: AccountTab) => void }) {
  return (
    <div role="tablist" aria-label="Account sections" className="flex gap-1 overflow-x-auto border-b border-border">
      {ACCOUNT_TABS.map((tab) => {
        const active = tab.key === value;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`account-tab-${tab.key}`}
            aria-selected={active}
            aria-controls={`account-panel-${tab.key}`}
            onClick={() => onChange(tab.key)}
            className={cn(
              "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
