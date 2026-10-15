/** A plain centered page for public one-off screens (pay links, signup status): wordmark, theme, card. */

import Link from "next/link";

import { BanglaBotWordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

export function PublicShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className={cn("mx-auto flex flex-col gap-8 px-4 py-10 sm:px-6", wide ? "max-w-3xl" : "max-w-md")}>
        <div className="flex items-center justify-between">
          <Link href="/" aria-label="Home">
            <BanglaBotWordmark className="scale-75 origin-left" />
          </Link>
          <ThemeToggle />
        </div>
        <main id="main">{children}</main>
      </div>
    </div>
  );
}

/** Icon + title + one line, for success / error states. */
export function PublicNotice({ icon, title, children, tone = "default" }: { icon: React.ReactNode; title: string; children?: React.ReactNode; tone?: "default" | "success" | "error" }) {
  return (
    <div className="rounded-lg border border-border bg-card p-6 text-center">
      <span
        className={cn(
          "mx-auto inline-flex h-12 w-12 items-center justify-center rounded-full",
          tone === "success" ? "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300" : tone === "error" ? "bg-destructive/10 text-destructive" : "bg-accent text-accent-foreground",
        )}
      >
        {icon}
      </span>
      <h1 className="mt-4 text-xl font-semibold">{title}</h1>
      {children && <div className="mt-2 space-y-3 text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}
