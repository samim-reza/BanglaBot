"use client";

import { FormEvent, useMemo } from "react";
import { BookOpenText, Sparkles } from "lucide-react";

import { SectionCard, useDraft } from "@/components/portal/kit";
import { Counter, FormRow, SaveBar, useReportDirty, useSaver } from "@/components/settings/shared";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { merchantApi, type VerticalKey } from "@/services/api";

const KNOWLEDGE_MAX = 8000;
/** The agent reads the whole knowledge base; past this length, nudge the owner to keep it focused. */
const KNOWLEDGE_USED = 7000;

const KNOWLEDGE_EXAMPLES: Partial<Record<VerticalKey, string>> = {
  ecommerce: `About us: [Store name] sells [what you sell] online.
Delivery: [2–4 business days] within [country]; express delivery in [1 day] for [$9.99].
Payment: cash on delivery for orders under [$300]; cards and PayPal online.
Returns: free returns within [30 days] for unused items with tags; refunds within [5–7 days].
Exchanges: size exchanges are free.
Address changes: possible until the order is dispatched.
Support hours: [Monday–Saturday, 9am–7pm].
FAQ — Do you ship abroad? [Not yet — only within the country.]
FAQ — How do I track my order? [A tracking link is sent by SMS once it ships.]`,
  clinic: `Address: [450 Main Street, Suite 200, City] — [across from the station; free parking behind the building].
Opening hours: [Mon–Fri 8am–6pm, Sat 9am–1pm, closed Sunday].
Insurance: we accept [Aetna, Cigna, Blue Cross]; self-pay patients are welcome.
New patients: please arrive [15 minutes] early with a photo ID [and insurance card].
Cancellations: please give at least [24 hours] notice.
Walk-ins: seen only for urgent issues, subject to availability.
Test results: discussed at a follow-up visit, not over the phone.
FAQ — Do you see children? [Yes, our pediatrician sees children from birth to 16.]
FAQ — Is there wheelchair access? [Yes, step-free entrance and lift.]`,
  real_estate: `Office: [120 Harbor Drive, City]. Office hours [Mon–Sat 9am–6pm].
Areas we cover: [Downtown, Riverside, North Hills].
Fees: buyers pay [no agency fee]; sellers pay [a 3% commission, negotiable].
Rentals: [one month's deposit plus the first month's rent]; pets [allowed in some listings].
Viewings: always with a licensed agent; please bring a photo ID.
Mortgages: we work with [lender name] for pre-approvals.
Selling: free valuation visit within [48 hours].
FAQ — Can I view on Sunday? [By appointment only.]
FAQ — Are prices negotiable? [Some are — the agent confirms at the viewing.]`,
  home_service: `Company: [Name], licensed and insured in [areas].
Call-out charge: [$79], waived if you go ahead with the repair.
Payment: [cards, Apple Pay, cash]; payment after the job is done.
Warranty: [90-day] workmanship warranty on all repairs.
Arrival: the technician calls [30 minutes] before arriving.
Same-day visits: depend on availability.
Hours: [Mon–Sat 8am–6pm]; [no Sunday visits].
FAQ — Do you bring parts? [Common parts are on the van; others within 2 days.]
FAQ — Do you give quotes over the phone? [Only the call-out charge and the usual price range — the technician quotes after inspection.]`,
};

export function KnowledgeSection({ onSaved }: { onSaved?: () => void }) {
  const { merchant, vertical, refresh } = useWorkspace();
  const source = useMemo(() => ({ knowledge: merchant.knowledge ?? "" }), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("knowledge", dirty);
  const length = draft.knowledge.length;
  const catalogPlural = t(vertical.catalog_label_plural).toLowerCase();

  const insertExample = () => {
    const example = KNOWLEDGE_EXAMPLES[vertical.key] ?? KNOWLEDGE_EXAMPLES.ecommerce ?? "";
    if (draft.knowledge.trim() && !window.confirm("Replace your current text with the example? You can still discard it before saving.")) return;
    setDraft(() => ({ knowledge: example }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (length > KNOWLEDGE_MAX) {
      setError(`Keep it under ${KNOWLEDGE_MAX.toLocaleString("en-US")} characters.`);
      return;
    }
    void run(async () => {
      const updated = await merchantApi.updateMe({ knowledge: draft.knowledge.trim() });
      commit({ knowledge: updated.knowledge ?? "" });
      await refresh();
      onSaved?.();
    }, "Knowledge base saved.");
  };

  return (
    <SectionCard
      id="knowledge"
      icon={BookOpenText}
      title="Knowledge base"
      description="Facts your agent answers from. It never makes things up."
      info={
        <>
          Short, plain lines: address and directions, opening hours, payment and cancellation policies, frequent questions. Put what customers ask most at the top.
          {catalogPlural ? ` Your ${catalogPlural} are managed separately.` : ""} With the example, replace the [bracketed] parts.
        </>
      }
    >
      <form className="grid gap-3" onSubmit={submit} noValidate>
        <FormRow
          id="knowledge"
          label="Business information"
          aside={<Counter value={length} max={KNOWLEDGE_MAX} warnAt={KNOWLEDGE_USED} />}
          hint={length > KNOWLEDGE_USED ? "Getting long — keep to what callers actually ask." : undefined}
        >
          <Textarea
            id="knowledge"
            rows={12}
            maxLength={KNOWLEDGE_MAX}
            value={draft.knowledge}
            placeholder={"Address: …\nOpening hours: …\nPolicies: …\nFAQ — …"}
            className="font-mono text-[13px] leading-relaxed"
            aria-describedby={length > KNOWLEDGE_USED ? "knowledge-hint" : undefined}
            onChange={(e) => setDraft(() => ({ knowledge: e.target.value }))}
          />
        </FormRow>
        <div>
          <Button type="button" variant="outline" size="sm" onClick={insertExample}>
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Insert example
          </Button>
        </div>
        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} />
      </form>
    </SectionCard>
  );
}
