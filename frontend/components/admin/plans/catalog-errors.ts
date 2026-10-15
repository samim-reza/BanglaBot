/** A 422 from PUT /api/admin/plans/catalog, split into catalog-wide, per-row and per-field messages. */

export type CatalogErrors = {
  general: string[];
  /** "tiers.2" / "addons.0" → messages about the whole row. */
  rows: Record<string, string[]>;
  /** "tiers.2.price_month" → message. */
  fields: Record<string, string>;
};

export const NO_ERRORS: CatalogErrors = { general: [], rows: {}, fields: {} };

const clean = (msg: unknown) => String(msg ?? "").replace(/^Value error,\s*/i, "");

export function catalogErrors(error: unknown, fallback: string): CatalogErrors {
  const detail = (error as { body?: { detail?: unknown } } | null)?.body?.detail;
  if (typeof detail === "string") return { ...NO_ERRORS, general: [detail] };
  if (!Array.isArray(detail)) {
    const message = (error as { detail?: string } | null)?.detail;
    return { ...NO_ERRORS, general: [message || fallback] };
  }
  const out: CatalogErrors = { general: [], rows: {}, fields: {} };
  for (const item of detail as { loc?: unknown[]; msg?: unknown }[]) {
    const loc = (item.loc ?? []).filter((part) => part !== "body").map(String);
    const msg = clean(item.msg);
    if ((loc[0] === "tiers" || loc[0] === "addons") && loc.length >= 2 && /^\d+$/.test(loc[1])) {
      const row = `${loc[0]}.${loc[1]}`;
      if (loc.length >= 3) out.fields[`${row}.${loc.slice(2).join(".")}`] = msg;
      else (out.rows[row] ??= []).push(msg);
    } else {
      out.general.push(msg);
    }
  }
  return out;
}

/** Field messages of one row, as a flat list (for the row's error line). */
export function rowMessages(errors: CatalogErrors, row: string): string[] {
  const own = errors.rows[row] ?? [];
  const fields = Object.entries(errors.fields)
    .filter(([path]) => path.startsWith(`${row}.`))
    .map(([path, msg]) => `${path.slice(row.length + 1)}: ${msg}`);
  return [...own, ...fields];
}
