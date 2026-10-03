import { cn } from "@/lib/utils";

/** Page-width wrapper shared by every marketing section. */
export function Container({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-4 sm:px-6", className)}>{children}</div>;
}

export function Section({
  id,
  tone = "default",
  className,
  children,
  labelledBy,
}: {
  id?: string;
  tone?: "default" | "muted" | "card";
  className?: string;
  children: React.ReactNode;
  labelledBy?: string;
}) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={cn(
        "scroll-mt-20 py-16 sm:py-20",
        tone === "muted" && "border-y border-border bg-surface",
        tone === "card" && "border-y border-border bg-card",
        className,
      )}
    >
      <Container>{children}</Container>
    </section>
  );
}

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cn("text-xs font-semibold uppercase tracking-[0.14em] text-primary-dark", className)}>{children}</p>
  );
}

export function SectionHeading({
  id,
  eyebrow,
  title,
  subtitle,
  align = "center",
  as: Tag = "h2",
  className,
}: {
  id?: string;
  eyebrow?: string;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  align?: "center" | "left";
  as?: "h1" | "h2";
  className?: string;
}) {
  return (
    <div className={cn("max-w-2xl", align === "center" && "mx-auto text-center", className)}>
      {eyebrow && <Eyebrow className="mb-3">{eyebrow}</Eyebrow>}
      <Tag
        id={id}
        className={cn(
          "text-balance font-bold tracking-tight text-foreground",
          Tag === "h1" ? "text-3xl sm:text-4xl lg:text-5xl" : "text-2xl sm:text-3xl",
        )}
      >
        {title}
      </Tag>
      {subtitle && <p className="mt-4 text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">{subtitle}</p>}
    </div>
  );
}

/** Hero band at the top of inner pages. */
export function PageHero({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section className="relative overflow-hidden border-b border-border">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_80%_at_50%_0%,hsl(var(--tint))_0%,transparent_70%)]"
      />
      <Container className="relative py-14 sm:py-20">
        <SectionHeading as="h1" eyebrow={eyebrow} title={title} subtitle={subtitle} />
        {children && <div className="mt-8 flex flex-wrap items-center justify-center gap-3">{children}</div>}
      </Container>
    </section>
  );
}
