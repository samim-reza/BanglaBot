"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, KeyRound, ShieldCheck } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { adminApi, formatApiError, isApiRequestError, saveAdminSession } from "@/services/api";

/** The API asks for the authenticator code with 401 + `X-2FA-Required: totp`. */
function needsCode(err: unknown): boolean {
  if (!isApiRequestError(err) || err.status !== 401) return false;
  return err.headers?.get("X-2FA-Required") === "totp" || /two-factor code required/i.test(err.detail);
}

/** Admin sign-in: username + password, then a 6-digit code when two-factor sign-in is on. */
export function AdminLoginForm() {
  const router = useRouter();
  const toast = useAppToast();
  const expired = useSearchParams().get("expired") === "1";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"password" | "code">("password");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await adminApi.login(username.trim(), password, step === "code" ? code.trim() : "");
      saveAdminSession(result.token);
      setError(null);
      toast.success("Signed in.");
      router.replace("/admin");
    } catch (err) {
      if (step === "password" && needsCode(err)) {
        setStep("code");
        setError(null);
        return;
      }
      const message = formatApiError(err, "Login failed.");
      setError(step === "code" && isApiRequestError(err) && err.status === 401 ? "That code didn't work. Try the next one." : message);
      if (step === "code") setCode("");
    } finally {
      setBusy(false);
    }
  };

  const back = () => {
    setStep("password");
    setCode("");
    setError(null);
  };

  return (
    <div className="mx-auto max-w-md space-y-4 py-10">
      <h1 className="text-2xl font-semibold tracking-normal">Platform admin</h1>
      {expired && !error && (
        <p role="status" className="rounded-md border border-border bg-card p-3 text-sm text-muted-foreground">
          Session expired — sign in again.
        </p>
      )}
      <ApiError message={error} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {step === "code" ? <ShieldCheck className="h-4 w-4" /> : <KeyRound className="h-4 w-4" />}
            {step === "code" ? "Two-factor code" : "Sign in"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={submit}>
            {step === "password" ? (
              <>
                <Input autoComplete="username" aria-label="Username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" required />
                <Input
                  aria-label="Password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  type="password"
                  required
                />
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">Enter the 6-digit code from your authenticator app.</p>
                <Input
                  autoFocus
                  aria-label="Authenticator code"
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="123456"
                  className="text-center font-mono text-lg tracking-[0.4em]"
                  required
                />
              </>
            )}
            <Button className="w-full" type="submit" disabled={busy || (step === "code" && code.length !== 6)}>
              {busy ? "Signing in…" : step === "code" ? "Verify" : "Sign in"}
            </Button>
            {step === "code" && (
              <Button type="button" variant="ghost" className="w-full" onClick={back} disabled={busy}>
                <ArrowLeft className="h-4 w-4" />
                Back
              </Button>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
