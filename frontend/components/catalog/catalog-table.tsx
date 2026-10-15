"use client";

import { useMemo } from "react";
import { Pencil, Trash2 } from "lucide-react";

import { InfoTip } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import type { CatalogItem, FieldSpec } from "@/services/api";

import { ActiveSwitch } from "./active-switch";
import { catalogColumns } from "./columns";

/** The items of one catalog kind: name (+ a short secondary line), 2–4 key columns, the Offered switch, edit / delete. */
export function CatalogTable({
  items,
  fields,
  kind,
  currency,
  busyId,
  onEdit,
  onToggle,
  onRemove,
}: {
  items: CatalogItem[];
  fields: FieldSpec[];
  kind: string;
  currency: string;
  busyId: string | null;
  onEdit: (item: CatalogItem) => void;
  onToggle: (item: CatalogItem) => void;
  onRemove: (item: CatalogItem) => void;
}) {
  const columns = useMemo(() => catalogColumns(fields, kind, currency), [fields, kind, currency]);
  // A short secondary line under the name: the first plain text field not already shown as a column.
  const subtitleSpec = useMemo(
    () => fields.find((spec) => spec.key !== "name" && spec.type === "text" && !columns.some((column) => column.key === spec.key)),
    [fields, columns],
  );

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(fields.find((spec) => spec.key === "name")?.label, "Name")}</TableHead>
            {columns.map((column) => (
              <TableHead key={column.key} className={column.numeric ? "text-right" : undefined}>
                {column.label}
              </TableHead>
            ))}
            <TableHead>
              <span className="inline-flex items-center gap-1">
                Offered
                <InfoTip label="About offered">Switch off to hide it from callers without deleting it.</InfoTip>
              </span>
            </TableHead>
            <TableHead className="text-right">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => {
            const subtitle = subtitleSpec ? item.data?.[subtitleSpec.key] : null;
            return (
              <TableRow key={item.id} className={cn(!item.active && "text-muted-foreground")}>
                <TableCell className="min-w-44">
                  <button type="button" className="text-left font-medium hover:underline" onClick={() => onEdit(item)}>
                    {item.name}
                  </button>
                  {subtitle ? <div className="text-xs text-muted-foreground">{String(subtitle)}</div> : null}
                </TableCell>
                {columns.map((column) => {
                  const text = column.render(item);
                  return (
                    <TableCell
                      key={column.key}
                      className={cn(column.numeric ? "whitespace-nowrap text-right tabular-nums" : "max-w-[14rem] truncate")}
                      title={text}
                    >
                      {text}
                    </TableCell>
                  );
                })}
                <TableCell>
                  <div className="flex items-center gap-2">
                    <ActiveSwitch
                      checked={item.active}
                      disabled={busyId === item.id}
                      label={`Offer ${item.name} to callers`}
                      onChange={() => onToggle(item)}
                    />
                    <span className="text-xs text-muted-foreground">{item.active ? "On" : "Off"}</span>
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="ghost" onClick={() => onEdit(item)} aria-label={`Edit ${item.name}`}>
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                      <span className="hidden sm:inline">Edit</span>
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => onRemove(item)}
                      disabled={busyId === item.id}
                      aria-label={`Delete ${item.name}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
