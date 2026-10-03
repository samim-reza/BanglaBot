import { ADDON_GROUPS, ADDONS } from "@/lib/site-content";

/** The add-on catalog, grouped: chat channels, capacity, features & setup. */
export function AddonList() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {ADDON_GROUPS.map((group) => {
        const items = ADDONS.filter((addon) => addon.group === group.key);
        return (
          <section key={group.key} aria-labelledby={`addons-${group.key}`} className="overflow-hidden rounded-xl border border-border bg-card">
            <h3 id={`addons-${group.key}`} className="border-b border-border bg-surface px-5 py-3 text-sm font-semibold text-foreground">
              {group.label}
            </h3>
            <ul className="divide-y divide-border">
              {items.map((addon) => (
                <li key={addon.key} className="flex items-start justify-between gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <h4 className="font-semibold text-foreground">{addon.name}</h4>
                    <p className="mt-0.5 text-sm text-muted-foreground">{addon.summary}</p>
                    {addon.note && (
                      <p className="mt-2 inline-flex rounded-full bg-accent px-2 py-0.5 text-[11.5px] font-semibold text-accent-foreground">
                        {addon.note}
                      </p>
                    )}
                  </div>
                  <p className="shrink-0 whitespace-nowrap text-right text-sm font-semibold tabular-nums text-primary-dark">{addon.price}</p>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
