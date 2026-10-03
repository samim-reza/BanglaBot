import Link from "next/link";

import { BanglaBotMark } from "@/components/brand";
import { BRAND } from "@/lib/brand";
import { AGENTS, TRIAL_HREF } from "@/lib/site-content";

const PRODUCT_LINKS = [
  { href: "/solutions", label: "All solutions" },
  ...AGENTS.map((agent) => ({ href: `/solutions/${agent.slug}`, label: agent.name })),
];

const PLATFORM_LINKS = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/#demo", label: "Live demo" },
  { href: TRIAL_HREF, label: "Start free trial" },
];

const COMPANY_LINKS = [
  { href: "/contact", label: "Contact sales" },
  { href: "/security", label: "Safety & privacy" },
  { href: "/login", label: "Sign in" },
];

function FooterColumn({ title, links }: { title: string; links: { href: string; label: string }[] }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      <ul className="mt-3 space-y-2">
        {links.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-border bg-card">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="max-w-xs">
          <Link href="/" className="inline-flex items-center gap-2.5" aria-label={`${BRAND.name} home`}>
            <BanglaBotMark compact />
            <span className="text-lg font-bold tracking-tight text-primary-dark">{BRAND.name}</span>
          </Link>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{BRAND.tagline}</p>
          <a
            href={`mailto:${BRAND.salesEmail}`}
            className="mt-3 inline-block text-sm font-medium text-primary-dark hover:underline"
          >
            {BRAND.salesEmail}
          </a>
        </div>
        <FooterColumn title="Solutions" links={PRODUCT_LINKS} />
        <FooterColumn title="Product" links={PLATFORM_LINKS} />
        <FooterColumn title="Company" links={COMPANY_LINKS} />
      </div>
      <div className="border-t border-border">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-xs text-muted-foreground sm:px-6">
          <p>
            © {year} {BRAND.name}. All rights reserved.
          </p>
          <Link href="/admin/login" className="hover:text-foreground hover:underline">
            Admin
          </Link>
        </div>
      </div>
    </footer>
  );
}
