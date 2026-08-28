"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bot, KeyRound, ListOrdered, UserRound } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { Field, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  formatApiError,
  merchantApi,
  saveMerchantProfile,
  type Language,
  type Merchant,
  type MerchantSettingsInput,
  type VoicePersona,
} from "@/services/api";

const MAX_CALL_OPTIONS = [0, 60, 90, 120, 180, 240, 300, 420, 600];

type ProfileForm = { business_name: string; owner_name: string; phone: string; email: string; support_phone: string };
type AgentForm = {
  custom_greeting: string;
  language: Language;
  supported_languages: Language[];
  voice_persona: VoicePersona;
  verify_address: boolean;
  max_call_seconds: number;
  silence_hangup_secs: number;
};

function profileFrom(merchant: Merchant): ProfileForm {
  return {
    business_name: merchant.business_name ?? "",
    owner_name: merchant.owner_name ?? "",
    phone: merchant.phone ?? "",
    email: merchant.email ?? "",
    support_phone: merchant.support_phone ?? "",
  };
}

function agentFrom(merchant: Merchant): AgentForm {
  return {
    custom_greeting: merchant.custom_greeting ?? "",
    language: merchant.language ?? "bn",
    supported_languages: merchant.supported_languages?.length ? merchant.supported_languages : [merchant.language ?? "bn"],
    voice_persona: merchant.voice_persona ?? "female",
    verify_address: Boolean(merchant.verify_address),
    max_call_seconds: merchant.max_call_seconds ?? 0,
    silence_hangup_secs: merchant.silence_hangup_secs ?? 10,
  };
}

export default function SettingsPage() {
  const toast = useAppToast();
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [profile, setProfile] = useState<ProfileForm | null>(null);
  const [agent, setAgent] = useState<AgentForm | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<"profile" | "agent" | "password" | null>(null);
  const [password, setPassword] = useState({ current_password: "", new_password: "", confirm: "" });

  const loadPreview = useCallback(async () => {
    try {
      const preview = await merchantApi.flowPreview();
      setSteps(preview.steps);
    } catch {
      setSteps([]);
    }
  }, []);

  useEffect(() => {
    merchantApi
      .me()
      .then((me) => {
        setMerchant(me);
        setProfile(profileFrom(me));
        setAgent(agentFrom(me));
        setError(null);
      })
      .catch((err) => setError(formatApiError(err, "Could not load settings.")));
    void loadPreview();
  }, [loadPreview]);

  const applyUpdate = async (kind: "profile" | "agent", values: MerchantSettingsInput, message: string) => {
    setSaving(kind);
    try {
      const updated = await merchantApi.updateMe(values);
      saveMerchantProfile(updated);
      setMerchant(updated);
      setProfile(profileFrom(updated));
      setAgent(agentFrom(updated));
      toast.success(message);
      await loadPreview();
    } catch (err) {
      toast.error(formatApiError(err, "Could not save settings."));
    } finally {
      setSaving(null);
    }
  };

  const saveProfile = (event: FormEvent) => {
    event.preventDefault();
    if (!profile) return;
    void applyUpdate("profile", profile, "Profile saved.");
  };

  const saveAgent = (event: FormEvent) => {
    event.preventDefault();
    if (!agent) return;
    // The primary language is always one the agent understands.
    const supported = Array.from(new Set<Language>([agent.language, ...agent.supported_languages]));
    void applyUpdate("agent", { ...agent, supported_languages: supported }, "Agent settings saved.");
  };

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (password.new_password !== password.confirm) {
      toast.error("New passwords do not match.");
      return;
    }
    setSaving("password");
    try {
      await merchantApi.changePassword(password.current_password, password.new_password);
      setPassword({ current_password: "", new_password: "", confirm: "" });
      toast.success("Password changed.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not change the password."));
    } finally {
      setSaving(null);
    }
  };

  const toggleLanguage = (code: Language, checked: boolean) => {
    if (!agent) return;
    const next = checked ? Array.from(new Set([...agent.supported_languages, code])) : agent.supported_languages.filter((item) => item !== code);
    setAgent({ ...agent, supported_languages: next });
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle={merchant ? `Signed in as ${merchant.username}` : "Business profile, agent behaviour and password."} />
      <ApiError message={error} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserRound className="h-4 w-4" />
              Business profile
            </CardTitle>
            <CardDescription>The business name is what the agent introduces itself with.</CardDescription>
          </CardHeader>
          <CardContent>
            {profile && (
              <form className="grid gap-4" onSubmit={saveProfile}>
                <Field label="Business name">
                  <Input value={profile.business_name} onChange={(e) => setProfile({ ...profile, business_name: e.target.value })} required />
                </Field>
                <Field label="Owner name">
                  <Input value={profile.owner_name} onChange={(e) => setProfile({ ...profile, owner_name: e.target.value })} />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Phone">
                    <Input value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} inputMode="tel" />
                  </Field>
                  <Field label="Support phone" hint="Offered to customers who want to call back">
                    <Input value={profile.support_phone} onChange={(e) => setProfile({ ...profile, support_phone: e.target.value })} inputMode="tel" />
                  </Field>
                </div>
                <Field label="Email">
                  <Input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
                </Field>
                <div>
                  <Button type="submit" disabled={saving === "profile"}>
                    {saving === "profile" ? "Saving…" : "Save profile"}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-4 w-4" />
              Call agent
            </CardTitle>
            <CardDescription>How BanglaBot speaks to your customers.</CardDescription>
          </CardHeader>
          <CardContent>
            {agent && (
              <form className="grid gap-4" onSubmit={saveAgent}>
                <Field label="Custom greeting" hint="Leave blank for the default greeting using your business name.">
                  <Textarea
                    value={agent.custom_greeting}
                    onChange={(e) => setAgent({ ...agent, custom_greeting: e.target.value })}
                    rows={3}
                    placeholder="আসসালামু আলাইকুম, আমি Rahim Store থেকে বলছি…"
                  />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Primary language">
                    <Select value={agent.language} onChange={(e) => setAgent({ ...agent, language: e.target.value as Language })}>
                      <option value="bn">Bangla</option>
                      <option value="en">English</option>
                    </Select>
                  </Field>
                  <Field label="Voice persona">
                    <Select value={agent.voice_persona} onChange={(e) => setAgent({ ...agent, voice_persona: e.target.value as VoicePersona })}>
                      <option value="female">Female</option>
                      <option value="male">Male</option>
                    </Select>
                  </Field>
                </div>
                <fieldset className="flex flex-col gap-1.5 text-sm">
                  <legend className="font-medium">Also understand &amp; speak</legend>
                  <div className="flex flex-wrap gap-4">
                    {(["bn", "en"] as Language[]).map((code) => (
                      <label key={code} className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-[hsl(var(--primary))]"
                          checked={agent.supported_languages.includes(code) || agent.language === code}
                          disabled={agent.language === code}
                          onChange={(e) => toggleLanguage(code, e.target.checked)}
                        />
                        {code === "bn" ? "Bangla" : "English"}
                      </label>
                    ))}
                  </div>
                  <span className="text-xs text-muted-foreground">The agent switches if the customer answers in the other language.</span>
                </fieldset>
                <label className="flex items-start gap-3 rounded-md border p-3 text-sm">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]"
                    checked={agent.verify_address}
                    onChange={(e) => setAgent({ ...agent, verify_address: e.target.checked })}
                  />
                  <span>
                    <span className="font-medium">Verify delivery address</span>
                    <span className="block text-xs text-muted-foreground">Read the address back and ask the customer to confirm it before finishing.</span>
                  </span>
                </label>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Max call length">
                    <Select value={String(agent.max_call_seconds)} onChange={(e) => setAgent({ ...agent, max_call_seconds: Number(e.target.value) })}>
                      {MAX_CALL_OPTIONS.map((value) => (
                        <option key={value} value={value}>
                          {value === 0 ? "Default" : value % 60 === 0 ? `${value / 60} min` : `${value} s`}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Hang up after silence (s)" hint="5–30 seconds">
                    <Input
                      type="number"
                      min={5}
                      max={30}
                      value={agent.silence_hangup_secs}
                      onChange={(e) => setAgent({ ...agent, silence_hangup_secs: Number(e.target.value) })}
                    />
                  </Field>
                </div>
                <div>
                  <Button type="submit" disabled={saving === "agent"}>
                    {saving === "agent" ? "Saving…" : "Save agent settings"}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListOrdered className="h-4 w-4" />
              Call flow preview
            </CardTitle>
            <CardDescription>What the agent will do on each call, given the settings above.</CardDescription>
          </CardHeader>
          <CardContent>
            {steps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No preview available.</p>
            ) : (
              <ol className="list-decimal space-y-2 pl-5 text-sm">
                {steps.map((step, index) => (
                  <li key={`${index}-${step}`}>{step}</li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              Change password
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4" onSubmit={changePassword}>
              <Field label="Current password">
                <Input
                  type="password"
                  autoComplete="current-password"
                  value={password.current_password}
                  onChange={(e) => setPassword({ ...password, current_password: e.target.value })}
                  required
                />
              </Field>
              <Field label="New password">
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={password.new_password}
                  onChange={(e) => setPassword({ ...password, new_password: e.target.value })}
                  required
                  minLength={6}
                />
              </Field>
              <Field label="Confirm new password">
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={password.confirm}
                  onChange={(e) => setPassword({ ...password, confirm: e.target.value })}
                  required
                />
              </Field>
              <div>
                <Button type="submit" variant="outline" disabled={saving === "password"}>
                  {saving === "password" ? "Updating…" : "Update password"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
