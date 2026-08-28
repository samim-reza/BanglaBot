"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { BanglaBotWordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatApiError, merchantApi, merchantToken, saveMerchantSession } from "@/services/api";

export default function MerchantLoginPage() {
  const router = useRouter();
  const toast = useAppToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (merchantToken()) router.replace("/dashboard");
  }, [router]);

  const login = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await merchantApi.login(username.trim(), password);
      saveMerchantSession(result.token, result.merchant);
      setError(null);
      toast.success(`Signed in to ${result.merchant.business_name}.`);
      router.replace("/dashboard");
    } catch (err) {
      const message = formatApiError(err, "Login failed.");
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-md flex-col gap-6 px-6 py-12">
        <div className="flex items-center justify-between">
          <Link href="/">
            <BanglaBotWordmark />
          </Link>
          <ThemeToggle />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Merchant login</h1>
          <p className="mt-1 text-sm text-muted-foreground">Sign in to enter orders and place confirmation calls.</p>
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
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Username"
                required
              />
              <Input
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Password"
                type="password"
                required
              />
              <Button className="w-full" type="submit" disabled={busy}>
                {busy ? "Signing in…" : "Login"}
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-xs text-muted-foreground">
          Platform operator?{" "}
          <Link href="/admin/login" className="text-primary hover:underline">
            Admin login
          </Link>
        </p>
      </div>
    </div>
  );
}
