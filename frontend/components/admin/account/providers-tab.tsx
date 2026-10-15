"use client";

import { FormEvent, useEffect, useId, useState } from "react";
import { Save } from "lucide-react";

import { FormField, fieldProps } from "@/components/admin/form-bits";
import { DialogError } from "@/components/admin/overlay";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatApiError } from "@/services/api";
import { flowErrors } from "@/services/api/agentFlow";
import { adminFlowApi, STT_PROVIDERS, TTS_PROVIDERS, type ProviderChains } from "@/services/api/admin/flow";
import { systemApi, type VoiceEngine } from "@/services/api/admin/system";

const EMPTY: ProviderChains = { llm_chain: "", stt_chain: "", tts_chain: "" };
const FIELDS: { key: keyof ProviderChains; label: string; hint: string }[] = [
  { key: "llm_chain", label: "LLM chain", hint: "provider:model, comma-separated, first choice first" },
  { key: "stt_chain", label: "Speech-to-text chain", hint: STT_PROVIDERS.join(" · ") },
  { key: "tts_chain", label: "Text-to-speech chain", hint: TTS_PROVIDERS.join(" · ") },
];

/** The platform defaults, shown as placeholders. */
function defaults(engine: VoiceEngine | null): ProviderChains {
  if (!engine) return EMPTY;
  return {
    llm_chain: [...engine.llm.chain.map((link) => link.key), ...engine.llm.unconfigured].join(","),
    stt_chain: engine.stt.en.chain.join(","),
    tts_chain: engine.tts.en.chain.join(","),
  };
}

/** Per-account provider chains (superadmin); empty fields use the platform default. */
export function ProvidersTab({ merchantId, current }: { merchantId: string; current: Partial<ProviderChains> | undefined }) {
  const { can } = useAdminMe();
  const toast = useAppToast();
  const formId = useId();
  const [values, setValues] = useState<ProviderChains>({ ...EMPTY, ...current });
  const [engine, setEngine] = useState<VoiceEngine | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const editable = can("providers");

  useEffect(() => {
    systemApi.voiceEngine().then(setEngine).catch(() => undefined);
  }, []);

  const placeholders = defaults(engine);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors({});
    setError(null);
    try {
      const trimmed = { llm_chain: values.llm_chain.trim(), stt_chain: values.stt_chain.trim(), tts_chain: values.tts_chain.trim() };
      const result = await adminFlowApi.saveProviders(merchantId, trimmed);
      setValues({ ...EMPTY, ...result.provider_settings });
      toast.success("Providers saved.");
    } catch (err) {
      const parsed = flowErrors(err);
      if (parsed?.errors.length) setErrors(Object.fromEntries(parsed.errors.map((item) => [item.path, item.message])));
      else setError(formatApiError(err, "Could not save the providers."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Providers</CardTitle>
      </CardHeader>
      <CardContent>
        <form id={formId} className="space-y-4" onSubmit={submit}>
          {FIELDS.map((field) => {
            const id = `${formId}-${field.key}`;
            return (
              <FormField key={field.key} id={id} label={field.label} hint={field.hint} error={errors[field.key]}>
                <Input
                  {...fieldProps(id, errors[field.key], field.hint)}
                  className="font-mono text-[13px]"
                  value={values[field.key]}
                  placeholder={placeholders[field.key] ? `Default: ${placeholders[field.key]}` : "Platform default"}
                  onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                  disabled={!editable || busy}
                  spellCheck={false}
                  autoComplete="off"
                />
              </FormField>
            );
          })}
          <DialogError message={error} />
          {editable ? (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy}>
                <Save className="h-4 w-4" />
                {busy ? "Saving…" : "Save"}
              </Button>
              <Button type="button" variant="ghost" disabled={busy} onClick={() => setValues(EMPTY)} title="Clear every field to use the platform defaults (then save)">
                Use defaults
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Superadmins change providers.</p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
