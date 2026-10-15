"use client";

import { Fragment, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

import { rowMessages } from "./catalog-errors";
import { NumCell, SwitchCell, TextCell } from "./cells";
import { MoveButtons, RowTools } from "./row-actions";
import { TierDetails } from "./tier-details";
import type { CatalogEditor } from "./use-catalog";

/** Every tier, inline-editable; the rest of a tier's fields open below its row. */
export function TiersTable({ editor, editable }: { editor: CatalogEditor; editable: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const { tiers, errors, savedKeys, saved } = editor;
  const off = !editable;
  const err = (i: number, field: string) => errors.fields[`tiers.${i}.${field}`];

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">
                <span className="sr-only">Order</span>
              </TableHead>
              <TableHead>Key</TableHead>
              <TableHead>Name</TableHead>
              <TableHead className="text-right">$ / mo</TableHead>
              <TableHead className="text-right" title="0 = 10 × monthly">
                $ / yr
              </TableHead>
              <TableHead className="text-right">Minutes</TableHead>
              <TableHead className="text-right">Chats</TableHead>
              <TableHead className="text-right">Texts</TableHead>
              <TableHead className="text-right">Numbers</TableHead>
              <TableHead title="Shown on the website and at signup">Visible</TableHead>
              <TableHead title="Can be bought online">Online</TableHead>
              <TableHead className="w-16">
                <span className="sr-only">Details</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tiers.map((tier, i) => {
              const name = tier.name || tier.key || "new tier";
              const messages = rowMessages(errors, `tiers.${i}`);
              const set = (patch: Parameters<CatalogEditor["updateTier"]>[1]) => editor.updateTier(i, patch);
              return (
                <Fragment key={`${tier.key}-${i}`}>
                  <TableRow className={cn(!tier.visible && "bg-surface text-muted-foreground", messages.length > 0 && "bg-destructive/5")}>
                    <TableCell className="py-1.5">
                      <MoveButtons name={name} first={i === 0} last={i === tiers.length - 1} disabled={off} onMove={(step) => editor.move("tiers", i, step)} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      {savedKeys.tiers.has(tier.key) && tier.key ? (
                        <span className="font-mono text-xs">{tier.key}</span>
                      ) : (
                        <TextCell value={tier.key} onChange={(key) => set({ key })} label="Tier key" mono className="w-28" disabled={off} placeholder="key" error={err(i, "key")} />
                      )}
                    </TableCell>
                    <TableCell className="py-1.5">
                      <TextCell value={tier.name} onChange={(v) => set({ name: v })} label={`${name} name`} className="w-40" disabled={off} error={err(i, "name")} />
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={tier.price_month} onChange={(n) => set({ price_month: n })} label={`${name} monthly price`} step="0.01" disabled={off} error={err(i, "price_month")} />
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={tier.price_year} onChange={(n) => set({ price_year: n })} label={`${name} yearly price`} step="0.01" disabled={off} error={err(i, "price_year")} />
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={tier.included_minutes} onChange={(n) => set({ included_minutes: n })} label={`${name} minutes`} disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={tier.included_chats} onChange={(n) => set({ included_chats: n })} label={`${name} chats`} disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={tier.included_sms} onChange={(n) => set({ included_sms: n })} label={`${name} texts`} disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={tier.phone_numbers} onChange={(n) => set({ phone_numbers: n })} label={`${name} phone numbers`} className="w-16" disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      <SwitchCell checked={tier.visible} onChange={(v) => set({ visible: v })} label={`${name} visible`} disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      <SwitchCell checked={tier.checkout} onChange={(v) => set({ checkout: v })} label={`${name} buyable online`} disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      <RowTools name={name} open={open === i} onToggle={() => setOpen(open === i ? null : i)} onRemove={() => editor.remove("tiers", i)} disabled={off} />
                    </TableCell>
                  </TableRow>
                  {messages.length > 0 && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={12} className="py-1.5 text-xs font-medium text-destructive" role="alert">
                        {messages.join(" · ")}
                      </TableCell>
                    </TableRow>
                  )}
                  {open === i && saved && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={12} className="bg-surface">
                        <TierDetails tier={tier} options={saved.options} errors={errors} index={i} disabled={off} onChange={set} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {editable && (
        <Button variant="outline" size="sm" onClick={() => editor.add("tiers")}>
          <Plus className="h-3.5 w-3.5" />
          Add tier
        </Button>
      )}
    </div>
  );
}
