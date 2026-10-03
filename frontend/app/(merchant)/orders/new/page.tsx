"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { RecordForm } from "@/components/order-form";
import { PageHeader } from "@/components/page-header";
import { compactValues, defaultValues, type FormValues } from "@/components/schema-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, ordersApi, type OrderInput } from "@/services/api";

export default function NewRecordPage() {
  const router = useRouter();
  const toast = useAppToast();
  const { vertical } = useWorkspace();
  const singular = t(vertical.record_label, "Record");
  const plural = t(vertical.record_label_plural, "Records");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initial = useMemo(() => defaultValues(vertical.record_fields), [vertical.record_fields]);

  const submit = async (values: FormValues) => {
    setBusy(true);
    setError(null);
    try {
      // Vertical-only fields go top-level too; the API files them under `details`.
      const record = await ordersApi.create(compactValues(values) as OrderInput);
      toast.success(`${singular} saved.`);
      router.push(`/orders/${record.id}`);
    } catch (err) {
      const message = formatApiError(err, `Could not save the ${singular.toLowerCase()}.`);
      setError(message);
      toast.error(message);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title={`New ${singular.toLowerCase()}`}
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link href="/orders">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              {plural}
            </Link>
          </Button>
        }
      />
      <ApiError message={error} />
      <Card>
        <CardContent className="pt-5">
          <RecordForm initial={initial} submitLabel={`Save ${singular.toLowerCase()}`} busy={busy} onSubmit={submit} onCancel={() => router.push("/orders")} />
        </CardContent>
      </Card>
    </div>
  );
}
