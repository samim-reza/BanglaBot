import { ChevronDown } from "lucide-react";

import type { Faq } from "@/lib/site-content";

/** Native <details> accordion — works without JavaScript and is keyboard accessible. */
export function FaqList({ items }: { items: Faq[] }) {
  return (
    <div className="mx-auto max-w-3xl divide-y divide-border rounded-xl border border-border bg-card">
      {items.map((item) => (
        <details key={item.q} className="group px-5 py-1">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-md py-4 font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
            {item.q}
            <ChevronDown
              className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
              aria-hidden
            />
          </summary>
          <p className="pb-4 text-sm leading-relaxed text-muted-foreground">{item.a}</p>
        </details>
      ))}
    </div>
  );
}
