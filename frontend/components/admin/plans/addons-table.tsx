"use client";

import { Fragment, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { CatalogAddon } from "@/services/api/admin/plans";

import { AddonDetails } from "./addon-details";
import { rowMessages } from "./catalog-errors";
import { humanKey, NumCell, SwitchCell, TextCell } from "./cells";
import { MoveButtons, RowTools } from "./row-actions";
import type { CatalogEditor } from "./use-catalog";

const grantText = (addon: CatalogAddon) =>
  [addon.channel && humanKey(addon.channel), addon.feature && humanKey(addon.feature), ...Object.entries(addon.grants ?? {}).map(([k, v]) => `+${v.toLocaleString("en-US")} ${k}`)]
    .filter(Boolean)
    .join(" · ") || "—";

/** Every add-on, inline-editable; the rest of an add-on's fields open below its row. */
export function AddonsTable({ editor, editable }: { editor: CatalogEditor; editable: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const { addons, errors, savedKeys, saved } = editor;
  const off = !editable;
  const err = (i: number, field: string) => errors.fields[`addons.${i}.${field}`];

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
              <TableHead>Category</TableHead>
              <TableHead className="text-right">Price $</TableHead>
              <TableHead>Period</TableHead>
              <TableHead>Gives</TableHead>
              <TableHead title="Offered in the shop and at signup">Visible</TableHead>
              <TableHead className="w-16">
                <span className="sr-only">Details</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {addons.map((addon, i) => {
              const name = addon.name || addon.key || "new add-on";
              const messages = rowMessages(errors, `addons.${i}`);
              const set = (patch: Partial<CatalogAddon>) => editor.updateAddon(i, patch);
              return (
                <Fragment key={`${addon.key}-${i}`}>
                  <TableRow className={cn(!addon.visible && "bg-surface text-muted-foreground", messages.length > 0 && "bg-destructive/5")}>
                    <TableCell className="py-1.5">
                      <MoveButtons name={name} first={i === 0} last={i === addons.length - 1} disabled={off} onMove={(step) => editor.move("addons", i, step)} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      {savedKeys.addons.has(addon.key) && addon.key ? (
                        <span className="font-mono text-xs">{addon.key}</span>
                      ) : (
                        <TextCell value={addon.key} onChange={(key) => set({ key })} label="Add-on key" mono className="w-32" disabled={off} placeholder="key" error={err(i, "key")} />
                      )}
                    </TableCell>
                    <TableCell className="py-1.5">
                      <TextCell value={addon.name} onChange={(v) => set({ name: v })} label={`${name} name`} className="w-44" disabled={off} error={err(i, "name")} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      <Select className="h-8 w-28 text-[13px]" aria-label={`${name} category`} value={addon.category} disabled={off} onChange={(e) => set({ category: e.target.value })}>
                        {(saved?.options.categories ?? [addon.category]).map((c) => (
                          <option key={c} value={c}>
                            {humanKey(c)}
                          </option>
                        ))}
                      </Select>
                    </TableCell>
                    <TableCell className="py-1.5 text-right">
                      <NumCell value={addon.price} onChange={(n) => set({ price: n })} label={`${name} price`} step="0.01" disabled={off} error={err(i, "price")} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      <Select className="h-8 w-24 text-[13px]" aria-label={`${name} period`} value={addon.period} disabled={off} onChange={(e) => set({ period: e.target.value as CatalogAddon["period"] })}>
                        {(saved?.options.periods ?? ["month", "once"]).map((p) => (
                          <option key={p} value={p}>
                            {p === "month" ? "Monthly" : humanKey(p)}
                          </option>
                        ))}
                      </Select>
                    </TableCell>
                    <TableCell className="max-w-[16rem] truncate py-1.5 text-xs" title={grantText(addon)}>
                      {grantText(addon)}
                    </TableCell>
                    <TableCell className="py-1.5">
                      <SwitchCell checked={addon.visible} onChange={(v) => set({ visible: v })} label={`${name} visible`} disabled={off} />
                    </TableCell>
                    <TableCell className="py-1.5">
                      <RowTools name={name} open={open === i} onToggle={() => setOpen(open === i ? null : i)} onRemove={() => editor.remove("addons", i)} disabled={off} />
                    </TableCell>
                  </TableRow>
                  {messages.length > 0 && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={9} className="py-1.5 text-xs font-medium text-destructive" role="alert">
                        {messages.join(" · ")}
                      </TableCell>
                    </TableRow>
                  )}
                  {open === i && saved && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={9} className="bg-surface">
                        <AddonDetails addon={addon} options={saved.options} errors={errors} index={i} disabled={off} onChange={set} />
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
        <Button variant="outline" size="sm" onClick={() => editor.add("addons")}>
          <Plus className="h-3.5 w-3.5" />
          Add add-on
        </Button>
      )}
    </div>
  );
}
