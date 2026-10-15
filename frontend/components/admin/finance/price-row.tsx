"use client";

import { MiniSwitch } from "@/components/admin/form-bits";
import { TableCell, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { Price } from "@/services/api/admin/finance";

import { categoryLabel } from "./labels";
import type { PriceEdit } from "./use-pricebook";

const per = (p: Price) => `${p.per === 1 ? "" : `${p.per.toLocaleString("en-US")} `}${p.unit}${p.per === 1 ? "" : "s"}`;

/** One price: unit cost, list (shadow) price, free tier and billing increment, editable inline. */
export function PriceRow({ price, edit, onEdit, disabled }: { price: Price; edit: PriceEdit | undefined; onEdit: (patch: PriceEdit) => void; disabled: boolean }) {
  const value = <K extends keyof PriceEdit>(field: K) => (edit?.[field] ?? price[field]) as Price[K];
  const changed = (field: keyof PriceEdit) => edit !== undefined && field in edit;
  const money = (field: "unit_cost" | "list_price", label: string) => (
    <Input
      inputMode="decimal"
      aria-label={`${price.sku} ${label}`}
      className={cn("h-8 w-28 px-2 text-right font-mono text-[12.5px]", changed(field) && "border-primary ring-1 ring-primary")}
      value={String(value(field))}
      disabled={disabled}
      onChange={(e) => onEdit({ [field]: e.target.value.replace(/[^0-9.]/g, "") })}
    />
  );
  return (
    <TableRow className={cn(edit && "bg-accent/40")}>
      <TableCell className="min-w-[12rem]">
        <div className="font-mono text-[12.5px] font-semibold">{price.sku}</div>
        <div className="text-xs text-muted-foreground">
          {price.provider} · {categoryLabel(price.category)}
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">per {per(price)}</TableCell>
      <TableCell className="text-right">{money("unit_cost", "unit cost")}</TableCell>
      <TableCell className="text-right">{money("list_price", "list price")}</TableCell>
      <TableCell>
        <MiniSwitch checked={Boolean(value("free_tier"))} onChange={(v) => onEdit({ free_tier: v })} label={`${price.sku} free tier`} disabled={disabled} />
      </TableCell>
      <TableCell className="text-right">
        <Input
          type="number"
          min={0}
          aria-label={`${price.sku} billing increment (seconds)`}
          className={cn("h-8 w-20 px-2 text-right text-[12.5px]", changed("increment_secs") && "border-primary ring-1 ring-primary")}
          value={String(value("increment_secs"))}
          disabled={disabled}
          onChange={(e) => onEdit({ increment_secs: Number(e.target.value || 0) })}
        />
      </TableCell>
      <TableCell className="min-w-[10rem]">
        <Input
          aria-label={`${price.sku} note`}
          className={cn("h-8 px-2 text-[12.5px]", changed("note") && "border-primary ring-1 ring-primary")}
          value={String(value("note") ?? "")}
          maxLength={200}
          disabled={disabled}
          onChange={(e) => onEdit({ note: e.target.value })}
        />
      </TableCell>
    </TableRow>
  );
}
