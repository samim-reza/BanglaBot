/** Helpers for rendering a business engine's vocabulary and values. */

import type { FieldSpec, Label, OrderStatus, VerticalSpec } from "@/services/api";

/** The portal is English-first; Bangla labels are kept for later. */
export function t(label: Partial<Label> | null | undefined, fallback = ""): string {
  if (!label) return fallback;
  return label.en || label.bn || fallback;
}

const GENERIC_STATUS: Record<OrderStatus, string> = {
  pending: "Pending",
  calling: "Calling",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
  no_answer: "No answer",
  needs_review: "Needs review",
};

export function statusLabel(spec: VerticalSpec | null | undefined, status: OrderStatus | string): string {
  const override = spec?.status_labels?.[status as OrderStatus];
  return override ? t(override) : GENERIC_STATUS[status as OrderStatus] ?? status;
}

const OUTCOME_LABELS: Record<string, string> = {
  confirmed: "Confirmed",
  cancelled: "Cancelled",
  booked: "Booked",
  rescheduled: "Rescheduled",
  lead: "Lead captured",
  inquiry: "Questions only",
  not_interested: "Not interested",
  emergency: "Emergency",
  transfer: "Transferred",
  wrong_number: "Wrong number",
  relay: "Message relayed",
  unclear: "Needs follow-up",
  auto_dropped: "Caller silent",
  diverted: "Diverted",
  voicemail: "Voicemail",
  no_answer: "No answer",
};

export function outcomeLabel(outcome: string | null | undefined): string {
  if (!outcome) return "In progress";
  return OUTCOME_LABELS[outcome] ?? outcome.replace(/_/g, " ");
}

const CHANNEL_LABELS: Record<string, string> = {
  outbound: "Outbound call",
  inbound: "Inbound call",
  web: "Browser test call",
  chat: "Chat test",
  widget: "Website chat",
};

export function channelLabel(direction: string | null | undefined): string {
  return CHANNEL_LABELS[direction ?? ""] ?? (direction || "Call");
}

/** Money in the account's currency. */
export function money(amount: unknown, currency = "USD"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const numeric = Number(amount);
  if (Number.isNaN(numeric)) return String(amount);
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD", maximumFractionDigits: 2 }).format(numeric);
  } catch {
    return `${currency} ${numeric.toLocaleString("en-US")}`;
  }
}

const DAY_LABELS: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
export const WEEK_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export function daysLabel(value: unknown): string {
  if (!Array.isArray(value) || !value.length) return "—";
  return value.map((day) => DAY_LABELS[String(day)] ?? String(day)).join(", ");
}

/** A field value for tables / detail views. */
export function displayValue(spec: FieldSpec, value: unknown, opts: { currency?: string; catalogNames?: Record<string, string>; timezone?: string } = {}): string {
  if (value === null || value === undefined || value === "") return "—";
  switch (spec.type) {
    case "money":
      return money(value, opts.currency);
    case "days":
      return daysLabel(value);
    case "bool":
      return value ? "Yes" : "No";
    case "select": {
      const option = spec.options.find((item) => item.value === value);
      return option ? t(option.label) : String(value);
    }
    case "multiselect":
    case "list":
      return Array.isArray(value) ? value.join(", ") : String(value);
    case "catalog":
      return opts.catalogNames?.[String(value)] ?? String(value);
    case "datetime":
      return formatInZone(String(value), opts.timezone);
    default:
      return String(value);
  }
}

/** "Mon 12 Oct, 6:20 PM" in the account's time zone. */
export function formatInZone(value: string | null | undefined, timezone?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  try {
    return new Intl.DateTimeFormat("en-US", {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
      timeZone: timezone || undefined,
    }).format(date);
  } catch {
    return date.toLocaleString();
  }
}

/** ISO instant → "YYYY-MM-DDTHH:mm" wall-clock in `timezone` (for <input type="datetime-local">). */
export function toZonedInput(value: string | null | undefined, timezone?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone || undefined,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

/** "YYYY-MM-DDTHH:mm" wall-clock in `timezone` → ISO instant (UTC). */
export function fromZonedInput(local: string, timezone?: string): string | null {
  if (!local) return null;
  const [datePart, timePart = "00:00"] = local.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [hh, mm] = timePart.split(":").map(Number);
  const guess = Date.UTC(y, m - 1, d, hh, mm);
  if (!timezone) return new Date(y, m - 1, d, hh, mm).toISOString();
  // Offset of the zone at that instant: format the guess in the zone and diff.
  const asZone = toZonedInput(new Date(guess).toISOString(), timezone);
  const [zd, zt] = asZone.split("T");
  const [zy, zm, zdd] = zd.split("-").map(Number);
  const [zh, zmin] = zt.split(":").map(Number);
  const offset = Date.UTC(zy, zm - 1, zdd, zh, zmin) - guess;
  return new Date(guess - offset).toISOString();
}
