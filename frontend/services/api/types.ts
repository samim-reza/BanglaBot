/** Response shapes for the BanglaBot order-confirmation API. */

export type OrderStatus = "pending" | "calling" | "confirmed" | "cancelled" | "no_answer" | "needs_review";

export const ORDER_STATUSES: OrderStatus[] = ["pending", "calling", "confirmed", "cancelled", "no_answer", "needs_review"];

export type Language = "bn" | "en";
export type VoicePersona = "female" | "male";

export type Merchant = {
  id: string;
  business_name: string;
  owner_name: string | null;
  username: string;
  phone: string | null;
  email: string | null;
  support_phone: string | null;
  custom_greeting: string | null;
  language: Language;
  supported_languages: Language[];
  voice_persona: VoicePersona;
  verify_address: boolean;
  max_call_seconds: number;
  silence_hangup_secs: number;
  active: boolean;
  created_at: string;
};

export type MerchantSettingsInput = Partial<{
  business_name: string;
  owner_name: string;
  phone: string;
  email: string;
  support_phone: string;
  custom_greeting: string;
  language: Language;
  supported_languages: Language[];
  voice_persona: VoicePersona;
  verify_address: boolean;
  max_call_seconds: number;
  silence_hangup_secs: number;
}>;

export type Order = {
  id: string;
  merchant_id: string;
  order_ref: string | null;
  customer_name: string;
  customer_phone: string;
  address: string | null;
  items_summary: string | null;
  total_amount: string;
  currency: string;
  status: OrderStatus;
  notes: string | null;
  flow_data: Record<string, unknown>;
  call_attempts: number;
  last_call_at: string | null;
  created_at: string;
  /** Present on admin listings only. */
  merchant_name?: string;
};

export type OrderInput = {
  order_ref?: string;
  customer_name: string;
  customer_phone: string;
  address?: string;
  items_summary?: string;
  total_amount?: string;
  notes?: string;
};

export type OrderUpdate = Partial<OrderInput> & { status?: OrderStatus };

export type CallLog = {
  id: string;
  order_id: string;
  twilio_call_sid: string | null;
  recording_sid: string | null;
  call_status: string | null;
  outcome: string | null;
  transcript: string | null;
  language: string | null;
  duration_secs: number | null;
  final_node: string | null;
  created_at: string;
  /** Present on admin listings only. */
  merchant_name?: string;
  customer_name?: string;
  order_ref?: string | null;
};

export type OrderDetail = Order & { call_logs: CallLog[] };

export type OrderStats = {
  pending: number;
  calling: number;
  confirmed: number;
  cancelled: number;
  no_answer: number;
  needs_review: number;
  total: number;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type AdminOverview = {
  merchants: number;
  orders: number;
  calls_today: number;
  confirmed_today: number;
  [key: string]: number;
};

export type MerchantCreateInput = {
  business_name: string;
  username: string;
  password: string;
  owner_name?: string;
  phone?: string;
  email?: string;
  support_phone?: string;
  language?: Language;
};

export type MerchantAdminUpdate = MerchantSettingsInput & Partial<{ password: string; active: boolean }>;

/** Statuses in which a new confirmation call must not be placed. */
export function callLocked(status: OrderStatus | string): boolean {
  return status === "calling" || status === "confirmed" || status === "cancelled";
}
