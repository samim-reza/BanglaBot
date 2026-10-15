"use client";

import { FormEvent, useState } from "react";
import { ShieldCheck, ShieldOff } from "lucide-react";

import { CopyButton } from "@/components/admin/copy-button";
import { DialogError } from "@/components/admin/overlay";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { StatusChip } from "@/components/admin/status-chip";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatApiError } from "@/services/api";
import { adminUsersApi, type AdminMe, type TotpSetup } from "@/services/api/admin/users";

const group = (secret: string) => secret.replace(/(.{4})/g, "$1 ").trim();

function CodeInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <Input
      aria-label={label}
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={6}
      placeholder="123456"
      className="w-32 text-center font-mono tracking-[0.3em]"
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
    />
  );
}

/** Two-factor sign-in (TOTP): set up with an authenticator app, confirm with a code; turn off with a code. */
export function TwoFactorCard({ me }: { me: AdminMe }) {
  const { reload } = useAdminMe();
  const toast = useAppToast();
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (call: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setError(null);
    try {
      await call();
      setCode("");
      setSetup(null);
      await reload();
      toast.success(done);
    } catch (err) {
      setError(formatApiError(err, "That didn't work."));
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      setSetup(await adminUsersApi.totpSetup());
    } catch (err) {
      setError(formatApiError(err, "Could not start the setup."));
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (code.length !== 6) return;
    if (me.totp_enabled) void run(() => adminUsersApi.totpDisable(code), "Two-factor sign-in is off.");
    else void run(() => adminUsersApi.totpEnable(code), "Two-factor sign-in is on.");
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Two-factor sign-in</CardTitle>
        <StatusChip state={me.totp_enabled ? "ok" : "off"}>{me.totp_enabled ? "On" : "Off"}</StatusChip>
      </CardHeader>
      <CardContent className="space-y-4">
        {!me.totp_enabled && !setup && (
          <Button variant="outline" onClick={() => void start()} disabled={busy}>
            <ShieldCheck className="h-4 w-4" />
            Set up
          </Button>
        )}
        {setup && (
          <div className="space-y-3 rounded-md border border-border bg-surface p-3 text-sm">
            <p>Add this key to your authenticator app (Google Authenticator, 1Password, Authy…).</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-card px-2 py-1 font-mono text-[13px] tracking-wide">{group(setup.secret)}</code>
              <CopyButton value={setup.secret} label="Copy key" />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <a href={setup.otpauth_uri} className="break-all text-primary hover:underline" title="On a phone, opens the authenticator app">
                Open in authenticator
              </a>
              <CopyButton value={setup.otpauth_uri} label="Copy link" />
            </div>
          </div>
        )}
        {(setup || me.totp_enabled) && (
          <form className="flex flex-wrap items-center gap-2" onSubmit={submit}>
            <CodeInput value={code} onChange={setCode} label={me.totp_enabled ? "Code to turn off" : "Code from the app"} />
            {me.totp_enabled ? (
              <Button type="submit" variant="outline" disabled={busy || code.length !== 6} className="text-destructive hover:text-destructive">
                <ShieldOff className="h-4 w-4" />
                {busy ? "Turning off…" : "Turn off"}
              </Button>
            ) : (
              <Button type="submit" disabled={busy || code.length !== 6}>
                {busy ? "Checking…" : "Turn on"}
              </Button>
            )}
            {setup && (
              <Button type="button" variant="ghost" onClick={() => setSetup(null)} disabled={busy}>
                Cancel
              </Button>
            )}
          </form>
        )}
        <DialogError message={error} />
      </CardContent>
    </Card>
  );
}
