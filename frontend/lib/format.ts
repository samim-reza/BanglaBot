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

export function formatMoney(amount: string | number | null | undefined, currency = "USD"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const numeric = typeof amount === "number" ? amount : Number(amount);
  if (Number.isNaN(numeric)) return String(amount);
  const symbol = currency === "USD" ? "$" : `${currency} `;
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


/** "+16175550142" → "(617) 555-0142" for US / Canada numbers; other numbers are shown as stored. */
export function formatPhone(value: string | null | undefined): string {
  const raw = String(value ?? "").trim();
  const digits = raw.replace(/\D/g, "");
  const national = digits.length === 11 && digits.startsWith("1") ? digits.slice(1) : !raw.startsWith("+") && digits.length === 10 ? digits : "";
  return national ? `(${national.slice(0, 3)}) ${national.slice(3, 6)}-${national.slice(6)}` : raw;
}

/** "17:00" → "5 PM", "09:30" → "9:30 AM"; anything else is shown as stored. */
export function formatClock(value: string | null | undefined): string {
  const match = /^(\d{1,2}):(\d{2})/.exec(String(value ?? "").trim());
  if (!match) return String(value ?? "");
  const hours = Number(match[1]);
  const suffix = hours < 12 || hours === 24 ? "AM" : "PM";
  const hour12 = hours % 12 || 12;
  return match[2] === "00" ? `${hour12} ${suffix}` : `${hour12}:${match[2]} ${suffix}`;
}
