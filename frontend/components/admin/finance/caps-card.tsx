"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Save } from "lucide-react";

import { DialogError } from "@/components/admin/overlay";
import { StatusChip } from "@/components/admin/status-chip";
import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatApiError } from "@/services/api";
import { financeApi, type ProviderCap } from "@/services/api/admin/finance";

import { usd } from "./money";

/** Daily spend cap per provider (USD). Empty = no cap, 0 = blocked. */
export function CapsCard() {
  const toast = useAppToast();
  const [items, setItems] = useState<ProviderCap[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [newProvider, setNewProvider] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const install = useCallback((rows: ProviderCap[]) => {
    setItems(rows);
    setDrafts({});
  }, []);

  useEffect(() => {
    financeApi
      .caps()
      .then((result) => install(result.items))
      .catch((err) => setError(formatApiError(err, "Could not load the caps.")));
  }, [install]);

  const changed = Object.entries(drafts).filter(([provider, value]) => {
    const current = items?.find((row) => row.provider === provider)?.cap_usd ?? "";
    return value.trim() !== String(current ?? "");
  });

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const caps = Object.fromEntries(changed.map(([provider, value]) => [provider, value.trim() === "" ? null : value.trim()]));
      install((await financeApi.saveCaps(caps)).items);
      toast.success("Caps saved.");
    } catch (err) {
      setError(formatApiError(err, "Could not save the caps."));
    } finally {
      setBusy(false);
    }
  };

  const addProvider = () => {
    const name = newProvider.trim().toLowerCase();
    if (!name || items?.some((row) => row.provider === name)) return;
    setItems((rows) => [...(rows ?? []), { provider: name, cap_usd: null, spent_today_usd: "0", over_cap: false }]);
    setDrafts((d) => ({ ...d, [name]: "" }));
    setNewProvider("");
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle title="Calls skip a provider once it passes its cap for the day (UTC)">Daily spend caps</CardTitle>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead className="text-right">Spent today</TableHead>
            <TableHead className="text-right" title="Empty = no cap · 0 = blocked">
              Cap $ / day
            </TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items?.map((row) => (
            <TableRow key={row.provider}>
              <TableCell className="font-mono text-[13px] font-semibold">{row.provider}</TableCell>
              <TableCell className="text-right tabular-nums">{usd(Number(row.spent_today_usd))}</TableCell>
              <TableCell className="text-right">
                <Input
                  inputMode="decimal"
                  aria-label={`${row.provider} daily cap`}
                  className="ml-auto h-8 w-28 px-2 text-right"
                  placeholder="No cap"
                  value={drafts[row.provider] ?? row.cap_usd ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [row.provider]: e.target.value.replace(/[^0-9.]/g, "") }))}
                  disabled={busy}
                />
              </TableCell>
              <TableCell>
                {row.over_cap ? <StatusChip state="down">Over cap</StatusChip> : row.cap_usd === null ? <StatusChip state="off">No cap</StatusChip> : <StatusChip state="ok">Under</StatusChip>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <CardContent className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <Input className="h-8 w-40" placeholder="provider" value={newProvider} onChange={(e) => setNewProvider(e.target.value)} aria-label="Provider to cap" onKeyDown={(e) => e.key === "Enter" && addProvider()} />
        <Button variant="outline" size="sm" onClick={addProvider} disabled={!newProvider.trim()}>
          <Plus className="h-3.5 w-3.5" />
          Add
        </Button>
        <Button size="sm" className="ml-auto" onClick={() => void save()} disabled={busy || changed.length === 0}>
          <Save className="h-3.5 w-3.5" />
          {busy ? "Saving…" : "Save caps"}
        </Button>
        <div className="w-full">
          <DialogError message={error} />
        </div>
      </CardContent>
    </Card>
  );
}
