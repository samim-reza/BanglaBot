"use client";

import { useEffect, useState } from "react";

import { Switch } from "@/components/admin/form-bits";
import { DialogError } from "@/components/admin/overlay";
import { useAppToast } from "@/components/app-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatApiError } from "@/services/api";
import { plansApi, type SignupSettings } from "@/services/api/admin/plans";

/** Whether paid signups go live on their own (saved on each toggle). */
export function SignupSettingsCard({ editable }: { editable: boolean }) {
  const toast = useAppToast();
  const [settings, setSettings] = useState<SignupSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    plansApi
      .settings()
      .then(setSettings)
      .catch((err) => setError(formatApiError(err, "Could not load the signup settings.")));
  }, []);

  const save = async (next: SignupSettings) => {
    setBusy(true);
    setError(null);
    try {
      setSettings(await plansApi.saveSettings(next));
      toast.success("Signup settings saved.");
    } catch (err) {
      setError(formatApiError(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Signups</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {settings && (
          <>
            <Switch
              label="Activate paid signups automatically"
              description="Off: an admin approves each one."
              checked={settings.auto_activate}
              disabled={!editable || busy}
              onChange={(value) => void save({ ...settings, auto_activate: value })}
            />
            <Switch
              label="Wait for a verified email"
              description="Auto-activation waits until the owner verifies."
              checked={settings.require_verified_email}
              disabled={!editable || busy || !settings.auto_activate}
              onChange={(value) => void save({ ...settings, require_verified_email: value })}
            />
          </>
        )}
        <DialogError message={error} />
      </CardContent>
    </Card>
  );
}
