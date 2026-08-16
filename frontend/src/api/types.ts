export type OrderStatus =
  | "pending" | "calling" | "confirmed" | "cancelled" | "no_answer" | "needs_review";

export interface Order {
  id: string;
  merchant_id: string;
  order_ref: string;
  customer_name: string;
  customer_phone: string;
  address: string;
  items_summary: string;
  total_amount: string;
  status: OrderStatus;
  notes: string;
  call_attempts: number;
  last_call_at: string | null;
  created_at: string;
}

export interface CallLog {
  id: string;
  order_id: string | null;
  twilio_call_sid: string;
  recording_sid: string;
  call_status: string;
  outcome: string;
  transcript: string;
  duration_secs: number;
  created_at: string;
}

export interface OrderDetail extends Order {
  call_logs: CallLog[];
}

export interface Merchant {
  id: string;
  business_name: string;
  owner_name: string;
  username: string;
  phone: string;
  support_phone: string;
  email: string;
  custom_greeting: string;
  max_call_seconds: number;
  voice_tier: string;
  active: boolean;
  created_at: string;
}

export interface VoiceTier {
  key: string;
  name_bn: string;
  description_bn: string;
  multiplier: number;
  mode: "static" | "ai";
}

export interface InsightsDay {
  day: string; // YYYY-MM-DD (Asia/Dhaka)
  confirmed: number;
  cancelled: number;
  no_answer: number;
  other: number;
}

export interface CallInsights {
  days: number;
  totals: {
    calls: number;
    picked: number;
    confirmed: number;
    cancelled: number;
    no_answer: number;
    other: number;
    minutes: number;
    avg_duration_secs: number;
    pickup_rate: number;
    confirm_rate: number;
  };
  daily: InsightsDay[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const STATUS_LABELS: Record<OrderStatus, string> = {
  pending: "অপেক্ষমাণ",
  calling: "কল চলছে",
  confirmed: "নিশ্চিত",
  cancelled: "বাতিল",
  no_answer: "ধরেননি",
  needs_review: "পর্যালোচনা দরকার",
};

export type SubStatus = "trialing" | "active" | "past_due" | "canceled";
export type InvoiceStatus = "due" | "paid" | "void";
export type TicketStatus = "open" | "answered" | "closed";

export interface Plan {
  id: string;
  key: string;
  name_bn: string;
  price_monthly: string;
  max_calls_per_month: number;
  max_minutes_per_month: number;
  features: string[];
  trial_days: number;
  is_default_trial: boolean;
  active: boolean;
  sort_order: number;
  created_at: string;
}

export interface Subscription {
  id: string;
  merchant_id: string;
  plan_key: string;
  status: SubStatus;
  current_period_start: string;
  current_period_end: string;
  bonus_calls: number;
  bonus_minutes: number;
  note: string;
  canceled_at: string | null;
  created_at: string;
}

export interface BillingSummary {
  plan: Plan | null;
  subscription: Subscription | null;
  usage: {
    calls_used: number;
    minutes_used: number;
    call_limit: number;
    minute_limit: number;
  };
  invoices_due: number;
  bkash_number: string;
  support_phone: string;
  support_email: string;
}

export interface Invoice {
  id: string;
  merchant_id: string;
  number: string;
  amount_due: string;
  status: InvoiceStatus;
  period_start: string;
  period_end: string;
  line_items: { label: string; amount: number }[];
  payment_method: string;
  paid_at: string | null;
  created_at: string;
}

export interface AdminInvoice extends Invoice {
  merchant_name: string;
}

export interface Ticket {
  id: string;
  reference: string;
  merchant_id: string;
  subject: string;
  status: TicketStatus;
  priority: string;
  last_message_at: string;
  created_at: string;
}

export interface TicketMessage {
  id: string;
  ticket_id: string;
  author_role: string;
  author_name: string;
  body: string;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  messages: TicketMessage[];
}

export interface AdminTicket extends Ticket {
  merchant_name: string;
}

export interface AdminTicketDetail extends AdminTicket {
  messages: TicketMessage[];
}

export interface AuditLog {
  id: string;
  actor_role: string;
  actor_id: string;
  actor_name: string;
  action: string;
  detail: string;
  merchant_id: string | null;
  created_at: string;
}

export interface AdminMerchant extends Merchant {
  plan_key: string | null;
  plan_name_bn: string | null;
  sub_status: string | null;
  calls_used: number;
  call_limit: number;
}

export interface PlatformSettingsData {
  platform_name: string;
  support_email: string;
  support_phone: string;
  bkash_number: string;
  signup_enabled: boolean;
  trial_plan_key: string;
  entitlement_mode: string;
  updated_at: string;
}

export interface AdminCall {
  id: string;
  merchant_id: string;
  merchant_name: string;
  // Null when the order was deleted — the log survives for usage metering.
  order_id: string | null;
  order_ref: string | null;
  call_status: string;
  outcome: string;
  duration_secs: number;
  transcript: string;
  recording_sid: string;
  created_at: string;
}

export interface AdminStats {
  merchants: { total: number; active: number };
  orders: Record<string, number>;
  calls_month: { calls: number; minutes: number };
  mrr: number;
  open_tickets: number;
  due_invoices: number;
  plans: { key: string; name_bn: string; count: number }[];
  recent_logs: AuditLog[];
}

export const SUB_STATUS_LABELS: Record<SubStatus, string> = {
  trialing: "ট্রায়াল",
  active: "সক্রিয়",
  past_due: "বকেয়া",
  canceled: "বাতিল",
};

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  due: "বকেয়া",
  paid: "পরিশোধিত",
  void: "বাতিল",
};

export const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  open: "খোলা",
  answered: "উত্তর এসেছে",
  closed: "বন্ধ",
};

export interface CostRateItem {
  id: string;
  cost_key: string;
  label_bn: string;
  unit: string;
  rate_bdt: string;
  effective_from: string;
  created_by: string;
}

export interface FinanceOverview {
  month: string;
  revenue: { mrr: number; collected: number; outstanding: number };
  costs: {
    telephony_bdt: number;
    stt_bdt: number;
    tts_bdt: number;
    llm_bdt: number;
    call_total_bdt: number;
    fixed_bdt: number;
    total_bdt: number;
  };
  calls: { count: number; minutes: number; avg_cost_bdt: number };
  margin: { gross_bdt: number; pct: number };
  unit: { cost_per_minute_bdt: number };
  daily: { day: string; cost_bdt: number; calls: number }[];
  per_merchant: {
    merchant_id: string;
    merchant_name: string;
    plan_name_bn: string;
    revenue_bdt: number;
    cost_bdt: number;
    margin_bdt: number;
    calls: number;
    minutes: number;
  }[];
}
