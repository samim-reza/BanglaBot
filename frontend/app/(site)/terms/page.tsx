import type { Metadata } from "next";

import { LegalPage } from "@/components/site/legal-page";
import { TERMS } from "@/lib/site/legal-terms";

export const metadata: Metadata = { title: TERMS.title, description: TERMS.description };

export default function TermsPage() {
  return <LegalPage doc={TERMS} />;
}
