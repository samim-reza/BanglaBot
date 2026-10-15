import { displayValue, money, t } from "@/lib/vertical";
import type { CatalogItem, FieldSpec } from "@/services/api";

export type Column = { key: string; label: string; numeric?: boolean; render: (item: CatalogItem) => string };

/** The 2–4 fields that identify an item at a glance, per catalog kind (generic fallback otherwise). */
export const PREFERRED: Record<string, string[]> = {
  doctor: ["specialty", "days", "hours", "fee"],
  property: ["listing_type", "property_type", "location", "price"],
  service: ["category", "visit_charge", "price_range", "duration"],
};

export function catalogColumns(fields: FieldSpec[], kind: string, currency: string): Column[] {
  const byKey = new Map(fields.map((spec) => [spec.key, spec]));
  const fieldColumn = (spec: FieldSpec): Column => ({
    key: spec.key,
    label: t(spec.label),
    numeric: spec.type === "money" || spec.type === "number",
    render: (item) => displayValue(spec, item.data?.[spec.key], { currency }),
  });
  const columns: Column[] = [];
  for (const key of PREFERRED[kind] ?? []) {
    if (key === "hours" && byKey.has("start_time") && byKey.has("end_time")) {
      columns.push({
        key,
        label: "Hours",
        render: (item) => {
          const start = item.data?.start_time;
          const end = item.data?.end_time;
          return start || end ? `${start || "?"}–${end || "?"}` : "—";
        },
      });
    } else if (key === "price_range" && byKey.has("price_from")) {
      columns.push({
        key,
        label: "Usual price",
        numeric: true,
        render: (item) => {
          const from = item.data?.price_from;
          const to = item.data?.price_to;
          if (from === undefined || from === null || from === "") return "—";
          return to !== undefined && to !== null && to !== "" ? `${money(from, currency)}–${money(to, currency)}` : `from ${money(from, currency)}`;
        },
      });
    } else {
      const spec = byKey.get(key);
      if (spec) columns.push(fieldColumn(spec));
    }
  }
  if (!columns.length) {
    return fields
      .filter((spec) => spec.key !== "name" && spec.type !== "textarea" && spec.type !== "list")
      .slice(0, 3)
      .map(fieldColumn);
  }
  return columns.slice(0, 4);
}

export function downloadText(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
