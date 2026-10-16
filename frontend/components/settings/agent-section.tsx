"use client";

/** Settings → Agent: when the agent hangs up (voice, greeting and steps live on the Agent page). */

import { FormEvent, useMemo } from "react";
import Link from "next/link";
import { Bot } from "lucide-react";

import { SectionCard, SwitchRow, useDraft } from "@/components/portal/kit";
import { FormRow, SaveBar, useReportDirty, useSaver } from "@/components/settings/shared";
import { Select } from "@/components/ui/select";
import { useWorkspace } from "@/lib/workspace";
import { merchantApi, type Merchant } from "@/services/api";

const SILENCE_OPTIONS = [5, 6, 8, 10, 12, 15, 20, 25, 30];
const MAX_CALL_OPTIONS = [0, 120, 180, 240, 300, 420, 600, 900];

type AgentForm = {
  silence_hangup_secs: number;
  max_call_seconds: number;
  verify_address: boolean;
};

function agentFrom(merchant: Merchant): AgentForm {
  return {
    silence_hangup_secs: merchant.silence_hangup_secs || 10,
    max_call_seconds: merchant.max_call_seconds || 0,
    verify_address: Boolean(merchant.verify_address),
  };
}

function maxCallLabel(seconds: number): string {
  if (!seconds) return "Platform default";
  return seconds % 60 === 0 ? `${seconds / 60} minutes` : `${seconds} seconds`;
}

function withCurrent(options: number[], current: number): number[] {
  return options.includes(current) ? options : [...options, current].sort((a, b) => a - b);
}

export function AgentSection({ onSaved }: { onSaved?: () => void }) {
  const { merchant, vertical, entitlements, refresh } = useWorkspace();
  const source = useMemo(() => agentFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("agent", dirty);
  const isEcommerce = vertical.key === "ecommerce";
  // A chat-only plan has no phone agent: no call-length settings.
  const hasVoice = entitlements.channels.includes("voice");

  const patch = (values: Partial<AgentForm>) => setDraft((current) => ({ ...current, ...values }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const updated = await merchantApi.updateMe({
        ...(hasVoice ? { silence_hangup_secs: draft.silence_hangup_secs, max_call_seconds: draft.max_call_seconds } : {}),
        ...(isEcommerce ? { verify_address: draft.verify_address } : {}),
      });
      commit(agentFrom(updated));
      await refresh();
      onSaved?.();
    }, "Agent settings saved.");
  };

  const agentLink = (
    <>
      Voice and steps:{" "}
      <Link href="/agent" className="font-medium text-primary-dark hover:underline dark:text-primary">
        Agent
      </Link>
    </>
  );

  if (!hasVoice && !isEcommerce) {
    return (
      <SectionCard id="agent" icon={Bot} title="Agent" description={agentLink}>
        <p className="text-sm text-muted-foreground">Nothing else to set here.</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard id="agent" icon={Bot} title={hasVoice ? "Call handling" : "Behaviour"} description={agentLink}>
      <form className="grid gap-5" onSubmit={submit} noValidate>
        {hasVoice && (
          <div className="grid gap-4 sm:grid-cols-2">
            <FormRow
              id="silence_hangup_secs"
              label="Silence timeout"
              info="After this much silence the agent asks whether the caller can hear it; after the same again, it ends the call."
            >
              <Select
                id="silence_hangup_secs"
                value={String(draft.silence_hangup_secs)}
                onChange={(e) => patch({ silence_hangup_secs: Number(e.target.value) })}
              >
                {withCurrent(SILENCE_OPTIONS, draft.silence_hangup_secs).map((value) => (
                  <option key={value} value={value}>
                    {value} seconds
                  </option>
                ))}
              </Select>
            </FormRow>
            <FormRow id="max_call_seconds" label="Max call length" info="The agent politely wraps up a call that reaches this length.">
              <Select
                id="max_call_seconds"
                value={String(draft.max_call_seconds)}
                onChange={(e) => patch({ max_call_seconds: Number(e.target.value) })}
              >
                {withCurrent(MAX_CALL_OPTIONS, draft.max_call_seconds).map((value) => (
                  <option key={value} value={value}>
                    {maxCallLabel(value)}
                  </option>
                ))}
              </Select>
            </FormRow>
          </div>
        )}

        {isEcommerce && (
          <SwitchRow
            checked={draft.verify_address}
            onChange={(verify_address) => patch({ verify_address })}
            title="Verify delivery address"
            hint="Read back on confirmation calls."
          />
        )}

        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} />
      </form>
    </SectionCard>
  );
}
