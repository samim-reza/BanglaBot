"use client";

import { FormEvent, useState } from "react";
import { Eye, EyeOff, KeyRound, LoaderCircle, LogOut } from "lucide-react";

import { InfoTip, SectionCard } from "@/components/portal/kit";
import { FormRow, useSaver } from "@/components/settings/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { merchantApi, saveMerchantToken } from "@/services/api";

/** The backend's password policy (app/schemas/auth.py). */
export const MIN_PASSWORD = 10;

export function SecuritySection() {
  const { saving, error, setError, run } = useSaver();
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const mismatch = form.confirm.length > 0 && form.next !== form.confirm;
  const filled = form.current && form.next && form.confirm;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.current) return setError("Enter your current password.");
    if (form.next.length < MIN_PASSWORD) return setError(`The new password needs at least ${MIN_PASSWORD} characters.`);
    if (form.next !== form.confirm) return setError("The new passwords don't match.");
    if (form.next === form.current) return setError("Choose a password different from the current one.");
    void run(
      async () => {
        const result = await merchantApi.changePassword(form.current, form.next);
        // Other sessions are now signed out; the re-issued token keeps this browser in.
        if (result?.token) saveMerchantToken(result.token);
        setForm({ current: "", next: "", confirm: "" });
      },
      "Password changed.",
      "Could not change the password.",
    );
  };

  const type = show ? "text" : "password";
  return (
    <SectionCard id="security" icon={KeyRound} title="Password" description="Change the password you sign in with.">
      <form className="grid gap-4 sm:grid-cols-3" onSubmit={submit} noValidate>
        <FormRow id="current_password" label="Current password">
          <Input id="current_password" type={type} autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} />
        </FormRow>
        <FormRow id="new_password" label="New password" hint={`At least ${MIN_PASSWORD} characters.`}>
          <Input
            id="new_password"
            type={type}
            autoComplete="new-password"
            value={form.next}
            aria-describedby="new_password-hint"
            onChange={(e) => setForm({ ...form, next: e.target.value })}
          />
        </FormRow>
        <FormRow id="confirm_password" label="Confirm password" hint={mismatch ? "Doesn't match." : undefined}>
          <Input
            id="confirm_password"
            type={type}
            autoComplete="new-password"
            value={form.confirm}
            aria-invalid={mismatch}
            aria-describedby={mismatch ? "confirm_password-hint" : undefined}
            className={cn(mismatch && "border-destructive")}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })}
          />
        </FormRow>
        <div className="space-y-3 sm:col-span-3">
          {error && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" variant="outline" disabled={saving || !filled}>
              {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
              Change password
            </Button>
            <Button type="button" variant="ghost" size="sm" aria-pressed={show} onClick={() => setShow((value) => !value)}>
              {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
              {show ? "Hide passwords" : "Show passwords"}
            </Button>
          </div>
        </div>
      </form>
    </SectionCard>
  );
}

/** Revoke every session (stolen laptop, shared computer); this browser stays signed in. */
export function SessionsSection() {
  const { saving, error, run } = useSaver();
  const signOutEverywhere = () => {
    if (!window.confirm("Sign out on every device? You stay signed in here.")) return;
    void run(
      async () => {
        const result = await merchantApi.logoutAll();
        if (result?.token) saveMerchantToken(result.token);
      },
      "Signed out everywhere else.",
      "Could not sign out other sessions.",
    );
  };
  return (
    <SectionCard
      id="sessions"
      icon={LogOut}
      title="Sessions"
      info="Ends every other signed-in session — phones, other browsers, shared computers. You stay signed in here."
    >
      <div className="space-y-3">
        {error && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" disabled={saving} onClick={signOutEverywhere}>
            {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            Sign out everywhere
          </Button>
          <InfoTip label="About signing out everywhere">Changing your password does this too.</InfoTip>
        </div>
      </div>
    </SectionCard>
  );
}
