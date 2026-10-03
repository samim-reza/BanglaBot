import { FEATURES, type Feature } from "@/lib/site-content";

export function FeatureGrid({ features = FEATURES }: { features?: Feature[] }) {
  return (
    <ul className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
      {features.map((feature) => {
        const Icon = feature.icon;
        return (
          <li key={feature.title} className="flex gap-4">
            <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <Icon className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <h3 className="font-semibold text-foreground">{feature.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{feature.body}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
