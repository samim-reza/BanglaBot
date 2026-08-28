/** Small display helpers shared by merchant and admin screens. */

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export function formatMoney(amount: string | number | null | undefined, currency = "BDT"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const numeric = typeof amount === "number" ? amount : Number(amount);
  if (Number.isNaN(numeric)) return String(amount);
  const symbol = currency === "BDT" ? "৳" : `${currency} `;
  return `${symbol}${numeric.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return minutes ? `${minutes}m ${rest.toString().padStart(2, "0")}s` : `${rest}s`;
}

/** "needs_review" → "Needs review" */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const text = value.replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function languageLabel(code: string | null | undefined): string {
  if (code === "bn") return "Bangla";
  if (code === "en") return "English";
  return code ? code.toUpperCase() : "—";
}
