"use client";

import { FormEvent, useEffect, useId, useState } from "react";

import { FormField, Switch } from "@/components/admin/form-bits";
import { DialogError, Overlay } from "@/components/admin/overlay";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { formatApiError } from "@/services/api";
import { ADMIN_ROLES, type AdminRole } from "@/services/api/admin/common";
import { adminUsersApi, type AdminUser, type AdminUserUpdate } from "@/services/api/admin/users";

import { ROLE_HINTS } from "./role-pill";
import { ROLE_LABELS } from "@/components/admin/shell/permissions";

/** Create an admin (`user` = null) or edit one: role, active, password reset, 2FA reset. */
export function AdminUserDialog({
  open,
  user,
  selfId,
  onClose,
  onSaved,
}: {
  open: boolean;
  user: AdminUser | null;
  selfId: string | undefined;
  onClose: () => void;
  onSaved: (user: AdminUser, created: boolean) => void;
}) {
  const formId = useId();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AdminRole>("support");
  const [active, setActive] = useState(true);
  const [resetTotp, setResetTotp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setUsername(user?.username ?? "");
    setPassword("");
    setRole(user?.role ?? "support");
    setActive(user?.active ?? true);
    setResetTotp(false);
    setError(null);
  }, [open, user]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!user) {
        onSaved(await adminUsersApi.create({ username: username.trim(), password, role }), true);
      } else {
        const patch: AdminUserUpdate = {};
        if (role !== user.role) patch.role = role;
        if (active !== user.active) patch.active = active;
        if (password) patch.password = password;
        if (resetTotp) patch.reset_totp = true;
        onSaved(Object.keys(patch).length ? await adminUsersApi.update(user.id, patch) : user, false);
      }
    } catch (err) {
      setError(formatApiError(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  const self = Boolean(user && user.id === selfId);
  return (
    <Overlay
      open={open}
      onClose={onClose}
      busy={busy}
      size="sm"
      title={user ? `Edit ${user.username}` : "New admin"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={busy || (!user && (!username.trim() || !password))}>
            {busy ? "Saving…" : user ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <form id={formId} className="space-y-4" onSubmit={submit}>
        {!user && (
          <FormField id={`${formId}-u`} label="Username" required hint="Letters, digits and . _ @ -">
            <Input id={`${formId}-u`} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" pattern="[A-Za-z0-9_.@\-]{3,80}" required />
          </FormField>
        )}
        <FormField id={`${formId}-r`} label="Role" hint={ROLE_HINTS[role]}>
          <Select id={`${formId}-r`} value={role} onChange={(e) => setRole(e.target.value as AdminRole)} disabled={self}>
            {ADMIN_ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id={`${formId}-p`} label={user ? "New password" : "Password"} required={!user} hint={user ? "Leave empty to keep it" : undefined}>
          <Input id={`${formId}-p`} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required={!user} />
        </FormField>
        {user && (
          <>
            <Switch label="Active" description="Inactive admins can't sign in." checked={active} onChange={setActive} disabled={self} />
            {user.totp_enabled && (
              <Switch label="Reset two-factor" description="For a lost phone — they set it up again." checked={resetTotp} onChange={setResetTotp} />
            )}
          </>
        )}
        <DialogError message={error} />
      </form>
    </Overlay>
  );
}
