"use client";

import { FormEvent, useId, useState } from "react";
import { KeyRound, LogOut } from "lucide-react";

import { FormField } from "@/components/admin/form-bits";
import { ConfirmDialog, DialogError } from "@/components/admin/overlay";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import { formatApiError, saveAdminSession } from "@/services/api";
import { adminUsersApi, type AdminMe } from "@/services/api/admin/users";

import { RolePill } from "./role-pill";

/** The signed-in admin: change password, sign out every other session. */
export function MyAccountCard({ me }: { me: AdminMe }) {
  const toast = useAppToast();
  const id = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signOutAll, setSignOutAll] = useState(false);
  const mismatch = confirm.length > 0 && confirm !== next;

  const change = async (event: FormEvent) => {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      const result = await adminUsersApi.changePassword(current, next);
      saveAdminSession(result.token);
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password changed. Other sessions were signed out.");
    } catch (err) {
      setError(formatApiError(err, "Could not change the password."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="me" className="scroll-mt-20">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="flex items-center gap-2">
          {me.username}
          <RolePill role={me.role} />
        </CardTitle>
        <Button variant="outline" size="sm" onClick={() => setSignOutAll(true)}>
          <LogOut className="h-3.5 w-3.5" />
          Sign out everywhere
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {me.last_login_at && <p className="text-xs text-muted-foreground">Last sign-in {formatDateTime(me.last_login_at)}</p>}
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={change}>
          <FormField id={`${id}-cur`} label="Current password">
            <Input id={`${id}-cur`} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
          </FormField>
          <FormField id={`${id}-new`} label="New password">
            <Input id={`${id}-new`} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
          </FormField>
          <FormField id={`${id}-again`} label="Repeat" error={mismatch ? "Doesn't match." : null}>
            <Input id={`${id}-again`} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={mismatch || undefined} required />
          </FormField>
          <div className="sm:col-span-3">
            <Button type="submit" disabled={busy || !current || !next || mismatch}>
              <KeyRound className="h-4 w-4" />
              {busy ? "Saving…" : "Change password"}
            </Button>
          </div>
        </form>
        <DialogError message={error} />
      </CardContent>
      <ConfirmDialog
        open={signOutAll}
        onClose={() => setSignOutAll(false)}
        title="Sign out everywhere?"
        confirmLabel="Sign out others"
        busyLabel="Signing out…"
        onConfirm={async () => {
          const result = await adminUsersApi.logoutAll();
          saveAdminSession(result.token);
          setSignOutAll(false);
          toast.success("Every other session was signed out.");
        }}
      >
        <p>Every other browser signed in as {me.username} is signed out. This one stays signed in.</p>
      </ConfirmDialog>
    </Card>
  );
}
