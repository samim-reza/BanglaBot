import { PhoneCall } from "lucide-react";

import { BRAND } from "@/lib/brand";

/** Square icon mark used in headers. */
export function BanglaBotMark({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground ${
        compact ? "h-9 w-9" : "h-12 w-12"
      }`}
    >
      <PhoneCall className={compact ? "h-4 w-4" : "h-6 w-6"} />
    </span>
  );
}

/** Header wordmark with a surface subtitle. */
export function BanglaBotBrand({ subtitle = BRAND.product }: { subtitle?: string }) {
  return (
    <span className="hidden min-w-0 sm:block">
      <span className="block truncate text-base font-bold leading-tight text-primary-dark">{BRAND.name}</span>
      <span className="block truncate text-xs text-muted-foreground">{subtitle}</span>
    </span>
  );
}

/** Large wordmark for the landing and login pages. */
export function BanglaBotWordmark({ className = "", inverted = false }: { className?: string; inverted?: boolean }) {
  return (
    <div className={`inline-flex items-center gap-3 ${className}`}>
      <BanglaBotMark />
      <span className={`text-3xl font-bold tracking-tight sm:text-4xl ${inverted ? "text-white" : "text-primary-dark"}`}>
        {BRAND.name}
      </span>
    </div>
  );
}
