"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { adminApi, formatApiError, saveAdminSession } from "@/services/api";

export default function AdminLoginPage() {
  const router = useRouter();
  const toast = useAppToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await adminApi.login(username.trim(), password);
      saveAdminSession(result.token);
      setError(null);
      toast.success("Signed in as platform admin.");
      router.replace("/admin");
    } catch (err) {
      const message = formatApiError(err, "Login failed.");
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-4 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-normal">Platform admin</h1>
        <p className="mt-1 text-sm text-muted-foreground">Manage accounts, review records, calls and chats, and follow up on sales inquiries.</p>
      </div>
      <ApiError message={error} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4" />
            Sign in
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={login}>
            <Input
              autoComplete="username"
              aria-label="Username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Username"
              required
            />
            <Input
              aria-label="Password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              type="password"
              required
            />
            <Button className="w-full" type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <p className="text-center text-xs text-muted-foreground">
        Business owner?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Sign in to your portal
        </Link>
        <span aria-hidden="true"> · </span>
        <Link href="/" className="text-primary hover:underline">
          Back to the website
        </Link>
      </p>
    </div>
  );
}
