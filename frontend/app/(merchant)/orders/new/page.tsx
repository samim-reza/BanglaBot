"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { OrderForm, formValuesToInput, orderToFormValues, type OrderFormValues } from "@/components/order-form";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { formatApiError, ordersApi } from "@/services/api";

export default function NewOrderPage() {
  const router = useRouter();
  const toast = useAppToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (values: OrderFormValues) => {
    setBusy(true);
    try {
      const order = await ordersApi.create(formValuesToInput(values));
      toast.success("Order created.");
      router.push(`/orders/${order.id}`);
    } catch (err) {
      const message = formatApiError(err, "Could not create the order.");
      setError(message);
      toast.error(message);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="New order" subtitle="Enter the order as the customer placed it; the agent reads these details back on the call." />
      <ApiError message={error} />
      <Card>
        <CardContent className="pt-5">
          <OrderForm initial={orderToFormValues()} submitLabel="Create order" busy={busy} onSubmit={submit} onCancel={() => router.push("/orders")} />
        </CardContent>
      </Card>
    </div>
  );
}
