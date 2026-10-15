"use client";

import { FormEvent, useState } from "react";
import { CircleAlert } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { SchemaFields, compactValues, defaultValues, validateValues, type FormValues } from "@/components/schema-form";
import { Button } from "@/components/ui/button";
import { catalogApi, formatApiError, type CatalogItem, type FieldSpec } from "@/services/api";

import { Dialog } from "./dialog";

/** Add (`item` null) or edit one catalog item. `kind` is only sent on create, and only when the vertical has several kinds. */
export function ItemDialog({
  item,
  fields,
  singular,
  kind,
  timezone,
  onClose,
  onSaved,
}: {
  item: CatalogItem | null;
  fields: FieldSpec[];
  singular: string;
  kind?: string;
  timezone: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useAppToast();
  const [values, setValues] = useState<FormValues>(() => (item ? { ...(item.data ?? {}), name: item.name } : defaultValues(fields)));
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const problem = validateValues(fields, values);
    if (problem) {
      setFormError(problem);
      return;
    }
    const { name, ...rest } = values;
    setSaving(true);
    setFormError(null);
    try {
      if (item) {
        // Cleared optional fields are sent as "" so the API removes them.
        await catalogApi.update(item.id, { name: String(name ?? "").trim(), data: rest });
        toast.success(`${singular} updated.`);
      } else {
        await catalogApi.create({ name: String(name ?? "").trim(), data: compactValues(rest) }, kind);
        toast.success(`${singular} added.`);
      }
      onSaved();
    } catch (err) {
      setFormError(formatApiError(err, `Could not save the ${singular.toLowerCase()}.`));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog title={item ? `Edit ${item.name}` : `Add ${singular.toLowerCase()}`} onClose={() => (saving ? undefined : onClose())}>
      <form className="flex min-h-0 flex-1 flex-col" onSubmit={save} noValidate>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          <SchemaFields
            specs={fields}
            values={values}
            onChange={(next) => {
              setValues(next);
              if (formError) setFormError(null);
            }}
            timezone={timezone}
            disabled={saving}
          />
        </div>
        <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          {formError ? (
            <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
              <CircleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
              {formError}
            </p>
          ) : (
            <span className="text-xs text-muted-foreground">* required</span>
          )}
          <div className="flex gap-2 sm:justify-end">
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : item ? "Save changes" : `Add ${singular.toLowerCase()}`}
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
