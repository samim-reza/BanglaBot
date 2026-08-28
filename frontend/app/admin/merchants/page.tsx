"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, Field, PageHeader } from "@/components/page-header";
import { BADGE_BASE, STATUS_STYLES } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { formatDate, languageLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  adminApi,
  formatApiError,
  type Language,
  type Merchant,
  type MerchantAdminUpdate,
  type MerchantCreateInput,
  type VoicePersona,
} from "@/services/api";

const MAX_CALL_OPTIONS = [0, 60, 90, 120, 180, 240, 300, 420, 600];

const EMPTY_CREATE: MerchantCreateInput = {
  business_name: "",
  username: "",
  password: "",
  owner_name: "",
  phone: "",
  email: "",
  support_phone: "",
  language: "bn",
};

type EditForm = {
  business_name: string;
  owner_name: string;
  phone: string;
  email: string;
  support_phone: string;
  custom_greeting: string;
  language: Language;
  supported_languages: Language[];
  voice_persona: VoicePersona;
  verify_address: boolean;
  max_call_seconds: number;
  silence_hangup_secs: number;
  active: boolean;
  password: string;
};

function editFrom(merchant: Merchant): EditForm {
  return {
    business_name: merchant.business_name ?? "",
    owner_name: merchant.owner_name ?? "",
    phone: merchant.phone ?? "",
    email: merchant.email ?? "",
    support_phone: merchant.support_phone ?? "",
    custom_greeting: merchant.custom_greeting ?? "",
    language: merchant.language ?? "bn",
    supported_languages: merchant.supported_languages?.length ? merchant.supported_languages : [merchant.language ?? "bn"],
    voice_persona: merchant.voice_persona ?? "female",
    verify_address: Boolean(merchant.verify_address),
    max_call_seconds: merchant.max_call_seconds ?? 0,
    silence_hangup_secs: merchant.silence_hangup_secs ?? 10,
    active: merchant.active !== false,
    password: "",
  };
}

function CreateMerchantForm({ onCreated }: { onCreated: () => void }) {
  const toast = useAppToast();
  const [form, setForm] = useState<MerchantCreateInput>(EMPTY_CREATE);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof MerchantCreateInput) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await adminApi.createMerchant({
        ...form,
        business_name: form.business_name.trim(),
        username: form.username.trim(),
      });
      toast.success(`Merchant "${form.business_name}" created.`);
      setForm(EMPTY_CREATE);
      onCreated();
    } catch (err) {
      toast.error(formatApiError(err, "Could not create the merchant."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      <Field label="Business name">
        <Input value={form.business_name} onChange={set("business_name")} required />
      </Field>
      <Field label="Owner name">
        <Input value={form.owner_name ?? ""} onChange={set("owner_name")} />
      </Field>
      <Field label="Username">
        <Input value={form.username} onChange={set("username")} autoComplete="off" required />
      </Field>
      <Field label="Password">
        <Input type="password" value={form.password} onChange={set("password")} autoComplete="new-password" required minLength={6} />
      </Field>
      <Field label="Phone">
        <Input value={form.phone ?? ""} onChange={set("phone")} inputMode="tel" />
      </Field>
      <Field label="Support phone">
        <Input value={form.support_phone ?? ""} onChange={set("support_phone")} inputMode="tel" />
      </Field>
      <Field label="Email">
        <Input type="email" value={form.email ?? ""} onChange={set("email")} />
      </Field>
      <Field label="Primary language">
        <Select value={form.language ?? "bn"} onChange={set("language")}>
          <option value="bn">Bangla</option>
          <option value="en">English</option>
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Button type="submit" disabled={busy}>
          <Plus className="h-4 w-4" />
          {busy ? "Creating…" : "Create merchant"}
        </Button>
      </div>
    </form>
  );
}

function EditMerchantDrawer({ merchant, onClose, onSaved }: { merchant: Merchant; onClose: () => void; onSaved: () => void }) {
  const toast = useAppToast();
  const [form, setForm] = useState<EditForm>(() => editFrom(merchant));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setForm(editFrom(merchant));
  }, [merchant]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const { password, ...rest } = form;
      const payload: MerchantAdminUpdate = {
        ...rest,
        supported_languages: Array.from(new Set<Language>([form.language, ...form.supported_languages])),
        ...(password ? { password } : {}),
      };
      await adminApi.updateMerchant(merchant.id, payload);
      toast.success("Merchant updated.");
      onSaved();
    } catch (err) {
      toast.error(formatApiError(err, "Could not update the merchant."));
    } finally {
      setBusy(false);
    }
  };

  const toggleLanguage = (code: Language, checked: boolean) =>
    setForm((current) => ({
      ...current,
      supported_languages: checked
        ? Array.from(new Set([...current.supported_languages, code]))
        : current.supported_languages.filter((item) => item !== code),
    }));

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/30">
      <button type="button" className="flex-1" aria-label="Close editor" onClick={onClose} />
      <div className="flex h-full w-full max-w-xl flex-col border-l border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">{merchant.business_name}</h2>
            <p className="text-xs text-muted-foreground">
              @{merchant.username} · created {formatDate(merchant.created_at)}
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close editor">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <form id="edit-merchant-form" className="flex-1 space-y-5 overflow-y-auto px-5 py-4" onSubmit={submit}>
          <label className="flex items-center justify-between rounded-md border p-3 text-sm">
            <span>
              <span className="font-medium">Active</span>
              <span className="block text-xs text-muted-foreground">Inactive merchants cannot sign in or place calls.</span>
            </span>
            <input
              type="checkbox"
              className="h-4 w-4 accent-[hsl(var(--primary))]"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
            />
          </label>

          <section className="space-y-3">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Profile</h3>
            <Field label="Business name">
              <Input value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} required />
            </Field>
            <Field label="Owner name">
              <Input value={form.owner_name} onChange={(e) => setForm({ ...form, owner_name: e.target.value })} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Phone">
                <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} inputMode="tel" />
              </Field>
              <Field label="Support phone">
                <Input value={form.support_phone} onChange={(e) => setForm({ ...form, support_phone: e.target.value })} inputMode="tel" />
              </Field>
            </div>
            <Field label="Email">
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Reset password" hint="Leave blank to keep the current password.">
              <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
          </section>

          <section className="space-y-3">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Call agent</h3>
            <Field label="Custom greeting">
              <Textarea value={form.custom_greeting} onChange={(e) => setForm({ ...form, custom_greeting: e.target.value })} rows={3} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Primary language">
                <Select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value as Language })}>
                  <option value="bn">Bangla</option>
                  <option value="en">English</option>
                </Select>
              </Field>
              <Field label="Voice persona">
                <Select value={form.voice_persona} onChange={(e) => setForm({ ...form, voice_persona: e.target.value as VoicePersona })}>
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
                      checked={form.supported_languages.includes(code) || form.language === code}
                      disabled={form.language === code}
                      onChange={(e) => toggleLanguage(code, e.target.checked)}
                    />
                    {languageLabel(code)}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[hsl(var(--primary))]"
                checked={form.verify_address}
                onChange={(e) => setForm({ ...form, verify_address: e.target.checked })}
              />
              Verify delivery address on the call
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Max call length">
                <Select value={String(form.max_call_seconds)} onChange={(e) => setForm({ ...form, max_call_seconds: Number(e.target.value) })}>
                  {MAX_CALL_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value === 0 ? "Default" : value % 60 === 0 ? `${value / 60} min` : `${value} s`}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Hang up after silence (s)">
                <Input
                  type="number"
                  min={5}
                  max={30}
                  value={form.silence_hangup_secs}
                  onChange={(e) => setForm({ ...form, silence_hangup_secs: Number(e.target.value) })}
                />
              </Field>
            </div>
          </section>
        </form>
        <div className="flex items-center justify-end gap-2 border-t px-5 py-3">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="edit-merchant-form" disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function AdminMerchantsPage() {
  const toast = useAppToast();
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Merchant | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    try {
      setMerchants(await adminApi.merchants());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load merchants."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (merchant: Merchant) => {
    if (!window.confirm(`Delete "${merchant.business_name}" and all of its orders and calls? This cannot be undone.`)) return;
    try {
      await adminApi.deleteMerchant(merchant.id);
      toast.success("Merchant deleted.");
      if (editing?.id === merchant.id) setEditing(null);
      void load();
    } catch (err) {
      toast.error(formatApiError(err, "Could not delete the merchant."));
    }
  };

  const toggleActive = async (merchant: Merchant) => {
    try {
      await adminApi.updateMerchant(merchant.id, { active: !merchant.active });
      toast.success(merchant.active ? "Merchant deactivated." : "Merchant activated.");
      void load();
    } catch (err) {
      toast.error(formatApiError(err, "Could not update the merchant."));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Merchants"
        subtitle="Every business using BanglaBot to confirm orders."
        actions={
          <Button onClick={() => setShowCreate((value) => !value)} variant={showCreate ? "outline" : "default"}>
            <Plus className="h-4 w-4" />
            {showCreate ? "Hide form" : "New merchant"}
          </Button>
        }
      />
      <ApiError message={error} />

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle>Create merchant</CardTitle>
            <CardDescription>The merchant signs in with the username and password you set here.</CardDescription>
          </CardHeader>
          <CardContent>
            <CreateMerchantForm
              onCreated={() => {
                setShowCreate(false);
                void load();
              }}
            />
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading merchants…</p>
      ) : merchants.length === 0 ? (
        <EmptyState title="No merchants yet">Create the first merchant to get started.</EmptyState>
      ) : (
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Business</TableHead>
                <TableHead>Username</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Language</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {merchants.map((merchant) => (
                <TableRow key={merchant.id}>
                  <TableCell>
                    <div className="font-medium">{merchant.business_name}</div>
                    {merchant.owner_name && <div className="text-xs text-muted-foreground">{merchant.owner_name}</div>}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{merchant.username}</TableCell>
                  <TableCell className="text-muted-foreground">
                    <div>{merchant.phone || "—"}</div>
                    {merchant.email && <div className="text-xs">{merchant.email}</div>}
                  </TableCell>
                  <TableCell>{languageLabel(merchant.language)}</TableCell>
                  <TableCell>
                    <button
                      type="button"
                      onClick={() => void toggleActive(merchant)}
                      className={cn(BADGE_BASE, merchant.active ? STATUS_STYLES.active : STATUS_STYLES.inactive)}
                      title="Toggle active"
                    >
                      {merchant.active ? "Active" : "Inactive"}
                    </button>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{formatDate(merchant.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="outline" onClick={() => setEditing(merchant)}>
                        <Pencil className="h-3.5 w-3.5" />
                        Edit
                      </Button>
                      <Button size="sm" variant="ghost" className="text-destructive" onClick={() => void remove(merchant)} aria-label="Delete merchant">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {editing && (
        <EditMerchantDrawer
          merchant={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      )}
    </div>
  );
}
