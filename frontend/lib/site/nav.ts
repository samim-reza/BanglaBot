/** Website navigation and the two calls to action used everywhere. */

export const SITE_NAV = [
  { href: "/solutions", label: "Solutions" },
  { href: "/pricing", label: "Pricing" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/contact", label: "Contact sales" },
] as const;

/** Self-serve signup; solution pages add ?vertical=<key>, pricing adds ?plan=. */
export const TRIAL_HREF = "/get-started";
export const SALES_HREF = "/contact";
