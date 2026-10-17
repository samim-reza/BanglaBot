import type { Metadata } from "next";

import { LegalPage } from "@/components/site/legal-page";
import { PRIVACY } from "@/lib/site/legal-privacy";

export const metadata: Metadata = { title: PRIVACY.title, description: PRIVACY.description };

export default function PrivacyPage() {
  return <LegalPage doc={PRIVACY} />;
}
