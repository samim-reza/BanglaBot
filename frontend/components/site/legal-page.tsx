import Link from "next/link";

import { Container, Eyebrow } from "@/components/site/section";
import type { LegalBlock, LegalDoc } from "@/lib/site/legal";

const LINK = /\[([^\]]+)\]\(([^)\s]+)\)/g;
const LINK_CLASS = "font-medium text-primary-dark underline underline-offset-2 hover:no-underline";

/** Plain text with `[label](href)` links; site paths use next/link. */
function Inline({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(LINK)) {
    const [whole, label, href] = match;
    const start = match.index ?? 0;
    if (start > last) parts.push(text.slice(last, start));
    parts.push(
      href.startsWith("/") ? (
        <Link key={start} href={href} className={LINK_CLASS}>
          {label}
        </Link>
      ) : (
        <a key={start} href={href} className={LINK_CLASS}>
          {label}
        </a>
      ),
    );
    last = start + whole.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

function Block({ block }: { block: LegalBlock }) {
  if (typeof block === "string") {
    return (
      <p>
        <Inline text={block} />
      </p>
    );
  }
  if ("list" in block) {
    return (
      <ul className="list-disc space-y-2 pl-5 marker:text-primary">
        {block.list.map((item) => (
          <li key={item}>
            <Inline text={item} />
          </li>
        ))}
      </ul>
    );
  }
  if ("terms" in block) {
    return (
      <dl className="divide-y divide-border rounded-xl border border-border bg-card">
        {block.terms.map(([label, detail]) => (
          <div key={label} className="grid gap-1 px-4 py-3 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4">
            <dt className="font-semibold text-foreground">{label}</dt>
            <dd>
              <Inline text={detail} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <thead className="bg-surface text-foreground">
          <tr>
            {block.table.head.map((cell) => (
              <th key={cell} scope="col" className="px-4 py-2.5 font-semibold">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-card">
          {block.table.rows.map((row) => (
            <tr key={row[0]}>
              {row.map((cell, index) =>
                index === 0 ? (
                  <th key={index} scope="row" className="px-4 py-2.5 font-medium text-foreground">
                    {cell}
                  </th>
                ) : (
                  <td key={index} className="px-4 py-2.5">
                    {cell}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Contents({ doc }: { doc: LegalDoc }) {
  return (
    <ol className="space-y-1.5 text-sm">
      {doc.sections.map((section) => (
        <li key={section.id}>
          <a href={`#${section.id}`} className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {section.title}
          </a>
        </li>
      ))}
    </ol>
  );
}

/** A legal page (privacy, terms): title, date, contents and numbered sections from structured data. */
export function LegalPage({ doc }: { doc: LegalDoc }) {
  return (
    <>
      <section className="border-b border-border bg-surface">
        <Container className="py-12 sm:py-16">
          <Eyebrow>Legal</Eyebrow>
          <h1 className="mt-3 text-balance text-3xl font-bold tracking-tight text-foreground sm:text-4xl">{doc.title}</h1>
          <p className="mt-3 text-sm text-muted-foreground">Last updated: {doc.updated}</p>
          <p className="mt-4 max-w-2xl text-pretty leading-relaxed text-muted-foreground">{doc.summary}</p>
        </Container>
      </section>

      <Container className="grid gap-10 py-12 sm:py-16 lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-14">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <details className="rounded-xl border border-border bg-card p-4 lg:hidden">
            <summary className="cursor-pointer text-sm font-semibold text-foreground">Contents</summary>
            <nav aria-label="Contents" className="mt-3">
              <Contents doc={doc} />
            </nav>
          </details>
          <nav aria-label="Contents" className="hidden lg:block">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-primary-dark">Contents</p>
            <Contents doc={doc} />
          </nav>
        </aside>

        <article className="min-w-0 max-w-3xl space-y-12">
          {doc.sections.map((section, index) => (
            <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="scroll-mt-24">
              <h2 id={`${section.id}-title`} className="text-xl font-bold tracking-tight text-foreground">
                <span className="mr-2 text-primary-dark">{index + 1}.</span>
                {section.title}
              </h2>
              <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-muted-foreground">
                {section.blocks.map((block, blockIndex) => (
                  <Block key={blockIndex} block={block} />
                ))}
              </div>
            </section>
          ))}
        </article>
      </Container>
    </>
  );
}
