"use client";

import { useRef, type KeyboardEvent } from "react";
import { Bot, Building2, CalendarDays, CreditCard, KeyRound, Smartphone, Webhook, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export type TabKey = "business" | "agent" | "payments" | "notifications" | "calendar" | "developers" | "security";

export type TabDef = { key: TabKey; label: string; icon: LucideIcon; /** Card ids inside (for the unsaved dots and #anchors). */ sections: string[] };

export const TABS: TabDef[] = [
  { key: "business", label: "Business", icon: Building2, sections: ["profile", "region", "business", "closures"] },
  { key: "agent", label: "Agent", icon: Bot, sections: ["agent", "knowledge"] },
  { key: "payments", label: "Payments", icon: CreditCard, sections: ["payments"] },
  { key: "notifications", label: "Notifications", icon: Smartphone, sections: ["alerts", "sms"] },
  { key: "calendar", label: "Calendar", icon: CalendarDays, sections: ["calendar"] },
  { key: "developers", label: "Developers", icon: Webhook, sections: ["webhooks"] },
  { key: "security", label: "Security", icon: KeyRound, sections: ["security", "sessions"] },
];

export function SettingsTabs({ tabs, active, dirty, onSelect }: { tabs: TabDef[]; active: TabKey; dirty: Record<string, boolean>; onSelect: (key: TabKey) => void }) {
  const refs = useRef<Partial<Record<TabKey, HTMLButtonElement | null>>>({});

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = tabs.findIndex((tab) => tab.key === active);
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    const key = tabs[next].key;
    onSelect(key);
    refs.current[key]?.focus();
  };

  return (
    <div role="tablist" aria-label="Settings" className="-mx-4 flex gap-1 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
      {tabs.map((tab) => {
        const selected = tab.key === active;
        const unsaved = tab.sections.some((id) => dirty[id]);
        return (
          <button
            key={tab.key}
            ref={(node) => {
              refs.current[tab.key] = node;
            }}
            type="button"
            role="tab"
            id={`settings-tab-${tab.key}`}
            aria-controls={`settings-panel-${tab.key}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(tab.key)}
            onKeyDown={onKeyDown}
            className={cn(
              "-mb-px inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              selected ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <tab.icon className="h-4 w-4 shrink-0" aria-hidden />
            {tab.label}
            {unsaved && (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
                <span className="sr-only">(unsaved changes)</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ tab, active, children }: { tab: TabKey; active: boolean; children: React.ReactNode }) {
  return (
    <div role="tabpanel" id={`settings-panel-${tab}`} aria-labelledby={`settings-tab-${tab}`} hidden={!active} className="space-y-6">
      {children}
    </div>
  );
}
