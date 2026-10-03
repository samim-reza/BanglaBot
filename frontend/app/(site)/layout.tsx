import { SiteShell } from "@/components/site/site-shell";

/** Public marketing pages share the site header and footer with the home page. */
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return <SiteShell>{children}</SiteShell>;
}
