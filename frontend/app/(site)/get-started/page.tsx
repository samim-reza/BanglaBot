import type { Metadata } from "next";

import { SignupWizard } from "@/components/signup/wizard";

export const metadata: Metadata = { title: "Get started" };

/** Self-serve signup: pick a business type, a plan and add-ons, create the account, pay. */
export default function GetStartedPage() {
  return (
    <section className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 lg:py-14">
      <h1 className="text-3xl font-bold tracking-tight">Get started</h1>
      <p className="mt-2 text-sm text-muted-foreground">Set up your agent in a few minutes.</p>
      <div className="mt-8">
        <SignupWizard />
      </div>
    </section>
  );
}
