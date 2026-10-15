"use client";

import { FormEvent, useMemo } from "react";
import { Building2 } from "lucide-react";

import { SectionCard, useDraft } from "@/components/portal/kit";
import { FormRow, SaveBar, useReportDirty, useSaver } from "@/components/settings/shared";
import { Input } from "@/components/ui/input";
import { useWorkspace } from "@/lib/workspace";
import { merchantApi, type Merchant } from "@/services/api";

type ProfileForm = { business_name: string; owner_name: string; phone: string; email: string; support_phone: string };

function profileFrom(merchant: Merchant): ProfileForm {
  return {
    business_name: merchant.business_name ?? "",
    owner_name: merchant.owner_name ?? "",
    phone: merchant.phone ?? "",
    email: merchant.email ?? "",
    support_phone: merchant.support_phone ?? "",
  };
}

export function ProfileSection({ onSaved }: { onSaved?: () => void }) {
  const { merchant, refresh } = useWorkspace();
  const source = useMemo(() => profileFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("profile", dirty);

  const set = (key: keyof ProfileForm) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.business_name.trim()) {
      setError("Business name is required.");
      return;
    }
    void run(async () => {
      const updated = await merchantApi.updateMe({
        business_name: draft.business_name.trim(),
        owner_name: draft.owner_name.trim(),
        phone: draft.phone.trim(),
        email: draft.email.trim(),
        support_phone: draft.support_phone.trim(),
      });
      commit(profileFrom(updated));
      await refresh();
      onSaved?.();
    }, "Business profile saved.");
  };

  return (
    <SectionCard id="profile" icon={Building2} title="Business profile" description="Your agent introduces itself with the business name.">
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit} noValidate>
        <FormRow id="business_name" label="Business name *">
          <Input id="business_name" value={draft.business_name} onChange={set("business_name")} maxLength={160} required autoComplete="organization" />
        </FormRow>
        <FormRow id="owner_name" label="Owner name">
          <Input id="owner_name" value={draft.owner_name} onChange={set("owner_name")} maxLength={120} autoComplete="name" />
        </FormRow>
        <FormRow id="phone" label="Phone" info="How the platform team reaches you.">
          <Input id="phone" type="tel" inputMode="tel" value={draft.phone} onChange={set("phone")} maxLength={32} autoComplete="tel" />
        </FormRow>
        <FormRow id="email" label="Email">
          <Input id="email" type="email" value={draft.email} onChange={set("email")} maxLength={160} autoComplete="email" />
        </FormRow>
        <FormRow
          id="support_phone"
          label="Transfer number"
          className="sm:col-span-2"
          info="Callers who ask for a person are put through to this number. Empty = the agent says a team member will call back."
        >
          <Input
            id="support_phone"
            type="tel"
            inputMode="tel"
            value={draft.support_phone}
            onChange={set("support_phone")}
            maxLength={32}
            placeholder="+1 415 555 0100"
          />
        </FormRow>
        <div className="sm:col-span-2">
          <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} />
        </div>
      </form>
    </SectionCard>
  );
}
