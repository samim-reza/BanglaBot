import { ADDONS } from "@/lib/site-content";

export function AddonList() {
  return (
    <ul className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
      {ADDONS.map((addon) => (
        <li key={addon.key} className="flex items-start justify-between gap-4 bg-card p-5">
          <div className="min-w-0">
            <h3 className="font-semibold text-foreground">{addon.name}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{addon.note}</p>
          </div>
          <p className="shrink-0 text-right text-sm font-semibold tabular-nums text-primary-dark">{addon.price}</p>
        </li>
      ))}
      {ADDONS.length % 2 === 1 && <li aria-hidden className="hidden bg-card sm:block" />}
    </ul>
  );
}
