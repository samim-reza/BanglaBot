export const CATEGORY_LABELS: Record<string, string> = {
  telephony: "Telephony",
  stt: "Speech-to-text",
  tts: "Text-to-speech",
  llm: "LLM",
  sms: "SMS",
  payments: "Payments",
  whatsapp: "WhatsApp",
};

export const categoryLabel = (key: string) => CATEGORY_LABELS[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** "2026-10" → "October 2026" */
export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, 1)));
}
