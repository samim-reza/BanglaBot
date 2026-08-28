"use client";

import { FormEvent, useState } from "react";

import { Field } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { Order, OrderInput } from "@/services/api";

export type OrderFormValues = {
  order_ref: string;
  customer_name: string;
  customer_phone: string;
  address: string;
  items_summary: string;
  total_amount: string;
  notes: string;
};

export function orderToFormValues(order?: Order | null): OrderFormValues {
  return {
    order_ref: order?.order_ref ?? "",
    customer_name: order?.customer_name ?? "",
    customer_phone: order?.customer_phone ?? "",
    address: order?.address ?? "",
    items_summary: order?.items_summary ?? "",
    total_amount: order?.total_amount ?? "",
    notes: order?.notes ?? "",
  };
}

export function formValuesToInput(values: OrderFormValues): OrderInput {
  return {
    order_ref: values.order_ref.trim(),
    customer_name: values.customer_name.trim(),
    customer_phone: values.customer_phone.trim(),
    address: values.address.trim(),
    items_summary: values.items_summary.trim(),
    total_amount: values.total_amount.trim(),
    notes: values.notes.trim(),
  };
}

/** The order fields, shared by "New order" and the editable detail view. */
export function OrderForm({
  initial,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: OrderFormValues;
  submitLabel: string;
  busy: boolean;
  onSubmit: (values: OrderFormValues) => void;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState<OrderFormValues>(initial);
  const set = (key: keyof OrderFormValues) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(values);
  };

  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      <Field label="Customer name" className="sm:col-span-1">
        <Input value={values.customer_name} onChange={set("customer_name")} placeholder="e.g. Rahim Uddin" required />
      </Field>
      <Field label="Customer phone" hint="Bangladeshi mobile number, e.g. 017XXXXXXXX or +8801XXXXXXXXX">
        <Input value={values.customer_phone} onChange={set("customer_phone")} placeholder="017XXXXXXXX" inputMode="tel" required />
      </Field>
      <Field label="Order reference" hint="Your store's order number (optional)">
        <Input value={values.order_ref} onChange={set("order_ref")} placeholder="#1042" />
      </Field>
      <Field label="Total amount (BDT)">
        <Input value={values.total_amount} onChange={set("total_amount")} placeholder="2400" inputMode="decimal" />
      </Field>
      <Field label="Delivery address" className="sm:col-span-2">
        <Textarea value={values.address} onChange={set("address")} placeholder="House, road, area, city" rows={2} />
      </Field>
      <Field label="Items summary" hint="What the agent reads back to the customer" className="sm:col-span-2">
        <Textarea value={values.items_summary} onChange={set("items_summary")} placeholder="2x Cotton panjabi (L), 1x Payjama" rows={3} />
      </Field>
      <Field label="Notes" hint="Internal notes, not read out on the call" className="sm:col-span-2">
        <Textarea value={values.notes} onChange={set("notes")} rows={2} />
      </Field>
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
