"use client";

import { useEffect, useState } from "react";

import { MiniSwitch } from "@/components/admin/form-bits";
import { DialogError } from "@/components/admin/overlay";
import { useAppToast } from "@/components/app-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { t } from "@/lib/vertical";
import { formatApiError } from "@/services/api";
import { plansApi, type OfferedVertical } from "@/services/api/admin/plans";

/** Which business types self-serve buyers may pick (saved on each toggle; at least one). */
export function VerticalsCard({ editable }: { editable: boolean }) {
  const toast = useAppToast();
  const [items, setItems] = useState<OfferedVertical[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    plansApi
      .verticals()
      .then((result) => setItems(result.items))
      .catch((err) => setError(formatApiError(err, "Could not load the business types.")));
  }, []);

  const toggle = async (key: string, on: boolean) => {
    if (!items) return;
    const offered = items.filter((item) => (item.key === key ? on : item.offered)).map((item) => item.key);
    setBusy(true);
    setError(null);
    try {
      setItems((await plansApi.saveVerticals(offered)).items);
      toast.success("Business types saved.");
    } catch (err) {
      setError(formatApiError(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  const offeredCount = items?.filter((item) => item.offered).length ?? 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle title="Business types new accounts can pick at signup">Business types offered</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border">
          {items?.map((item) => (
            <li key={item.key} className="flex items-center justify-between gap-3 py-2.5">
              <span className="min-w-0">
                <span className="block text-sm font-medium">{t(item.label, item.key)}</span>
                <span className="block truncate text-xs text-muted-foreground">{t(item.description)}</span>
              </span>
              <MiniSwitch
                checked={item.offered}
                onChange={(on) => void toggle(item.key, on)}
                label={`Offer ${t(item.label, item.key)}`}
                disabled={!editable || busy || (item.offered && offeredCount <= 1)}
              />
            </li>
          ))}
        </ul>
        <DialogError message={error} />
      </CardContent>
    </Card>
  );
}
