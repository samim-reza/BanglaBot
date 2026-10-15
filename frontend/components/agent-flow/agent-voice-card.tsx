"use client";

/** The Agent page header: call language, voice and the account greeting (PATCH /api/auth/me). */

import { FormEvent, useMemo } from "react";
import { Mic } from "lucide-react";

import { SectionCard, useDraft } from "@/components/portal/kit";
import { Counter, FormRow, SaveBar, Segmented, useSaver } from "@/components/settings/shared";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspace } from "@/lib/workspace";
import { merchantApi, type Language, type Merchant, type VoicePersona } from "@/services/api";

const GREETING_MAX = 300;

type VoiceForm = { language: Language; voice_persona: VoicePersona; custom_greeting: string };

function voiceFrom(merchant: Merchant): VoiceForm {
  return {
    language: merchant.language === "bn" ? "bn" : "en",
    voice_persona: merchant.voice_persona === "male" ? "male" : "female",
    custom_greeting: merchant.custom_greeting ?? "",
  };
}

export function AgentVoiceCard({ editableFlow, onSaved }: { editableFlow: boolean; onSaved: () => void }) {
  const { merchant, entitlements, refresh } = useWorkspace();
  const source = useMemo(() => voiceFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  // A chat-only plan has no phone agent: no voice choice.
  const hasVoice = entitlements.channels.includes("voice");
  const defaultGreeting = `Hello, thank you for ${hasVoice ? "calling" : "contacting"} ${merchant.business_name || "your business"}.`;
  const patch = (values: Partial<VoiceForm>) => setDraft((current) => ({ ...current, ...values }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (draft.custom_greeting.length > GREETING_MAX) {
      setError(`The greeting can be at most ${GREETING_MAX} characters.`);
      return;
    }
    void run(async () => {
      const updated = await merchantApi.updateMe({
        language: draft.language,
        // The chosen language is the call language (no auto-detect between languages).
        supported_languages: [draft.language],
        voice_persona: draft.voice_persona,
        custom_greeting: draft.custom_greeting.trim(),
      });
      commit(voiceFrom(updated));
      await refresh();
      onSaved();
    }, "Agent settings saved.");
  };

  return (
    <SectionCard id="voice" icon={Mic} title={hasVoice ? "Language & voice" : "Language & greeting"}>
      <form className="grid gap-5" onSubmit={submit} noValidate>
        <div className="grid gap-5 sm:grid-cols-2">
          <Segmented<Language>
            name="language"
            label="Language"
            value={draft.language}
            options={[
              { value: "en", label: "English" },
              { value: "bn", label: "Bangla" },
            ]}
            onChange={(language) => patch({ language })}
          />
          {hasVoice && (
            <Segmented<VoicePersona>
              name="voice_persona"
              label="Voice"
              value={draft.voice_persona}
              options={[
                { value: "female", label: "Female" },
                { value: "male", label: "Male" },
              ]}
              onChange={(voice_persona) => patch({ voice_persona })}
            />
          )}
        </div>
        <FormRow
          id="custom_greeting"
          label="Greeting"
          aside={<Counter value={draft.custom_greeting.length} max={GREETING_MAX} />}
          info={editableFlow ? "Said word for word. Rewording the Greeting step below takes over from this." : "Said word for word. Empty = default."}
        >
          <Textarea
            id="custom_greeting"
            rows={2}
            maxLength={GREETING_MAX}
            value={draft.custom_greeting}
            placeholder={defaultGreeting}
            onChange={(e) => patch({ custom_greeting: e.target.value })}
          />
        </FormRow>
        <SaveBar
          dirty={dirty}
          saving={saving}
          error={error}
          onReset={() => {
            reset();
            setError(null);
          }}
        />
      </form>
    </SectionCard>
  );
}
