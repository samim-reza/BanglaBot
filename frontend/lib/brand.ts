/** Brand constants — the product name lives here only, so a rename is one line. */
export const BRAND = {
  name: "Callisa",
  product: "AI voice & chat agents",
  tagline: "AI receptionists that answer every call, book the job and follow up.",
  /** Public contact address (NEXT_PUBLIC_CONTACT_EMAIL, read at build time). Empty = pages link to /contact instead. */
  contactEmail: (process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "").trim(),
} as const;
