/** Response shapes of the voice & chat agent platform API. */

export type OrderStatus = "pending" | "calling" | "confirmed" | "cancelled" | "no_answer" | "needs_review";

export const ORDER_STATUSES: OrderStatus[] = ["pending", "calling", "confirmed", "cancelled", "no_answer", "needs_review"];

export type Language = "bn" | "en";
export type VoicePersona = "female" | "male";
export type VerticalKey = "ecommerce" | "clinic" | "real_estate" | "home_service";
export type Direction = "inbound" | "outbound";
/** Where a call log came from: phone (outbound / inbound), browser test (web), chat test (chat), website widget. */
export type CallChannel = "outbound" | "inbound" | "web" | "chat" | "widget" | "whatsapp" | "messenger";

/** Where an account talks to customers. */
export type ChannelKey = "voice" | "web_chat" | "whatsapp" | "messenger";

/** A label in both portal languages. */
export type Label = { en: string; bn: string };

export type FieldType =
  | "text"
  | "textarea"
  | "phone"
  | "money"
  | "number"
  | "date"
  | "time"
  | "datetime"
  | "select"
  | "multiselect"
  | "days"
  | "catalog"
  | "bool"
  | "list";

/** One form field a vertical declares (records, catalog items, settings). */
export type FieldSpec = {
  key: string;
  label: Label;
  type: FieldType;
  required: boolean;
  options: { value: string; label: Label }[];
  help: Partial<Label>;
  placeholder: string;
  default: unknown;
  /** Shown as a column in the records table. */
  list_column: boolean;
  /** Record column it maps to; null = stored under `details`. */
  column: string | null;
};

/** A business engine: what records / catalog items are called and which fields they have. */
export type VerticalSpec = {
  key: VerticalKey;
  label: Label;
  description: Label;
  record_kind: string;
  record_label: Label;
  record_label_plural: Label;
  record_fields: FieldSpec[];
  catalog_kind: string;
  catalog_label: Partial<Label>;
  catalog_label_plural: Partial<Label>;
  catalog_fields: FieldSpec[];
  config_fields: FieldSpec[];
  config_defaults: Record<string, unknown>;
  status_labels: Partial<Record<OrderStatus, Label>>;
  outbound_label: Label;
  directions: Direction[];
  /** Records have a date/time (appointments, viewings, visits). */
  scheduled: boolean;
};

export type Region = {
  code: string;
  label: string;
  timezone: string;
  currency: string;
  emergency: string;
  calling_code: string;
  working_days: string[];
};

export type Plan = {
  key: string;
  name: string;
  price_month: number;
  included_minutes: number;
  overage_per_minute: number;
  included_chats: number;
  included_sms: number;
  phone_numbers: number;
  /** Channels the plan itself includes; the rest are add-ons. */
  channels: ChannelKey[];
  /** Feature keys the plan includes (e.g. "google_calendar"). */
  includes: string[];
  product: "voice" | "chat";
  tagline: string;
  features: string[];
  public: boolean;
  highlight: boolean;
};


/** Monthly allowances from the plan + add-ons; null = no limit. */
export type Limits = { minutes: number | null; chats: number | null; sms: number | null; numbers: number | null };

export type Usage = {
  plan: Plan;
  limits: Limits;
  period_start: string;
  minutes: number;
  calls: number;
  chats: number;
  /** Texts sent this month (queued, sent or delivered). */
  sms: number;
  minutes_left: number | null;
  overage_minutes: number;
};

export type WidgetSettings = { title?: string; subtitle?: string; color?: string; position?: "left" | "right" };

export type Merchant = {
  id: string;
  business_name: string;
  owner_name: string | null;
  username: string;
  phone: string | null;
  email: string | null;
  vertical: VerticalKey;
  vertical_config: Record<string, unknown>;
  knowledge: string;
  inbound_number: string;
  region: string;
  timezone: string;
  currency: string;
  emergency_number: string;
  support_phone: string | null;
  custom_greeting: string | null;
  language: Language;
  supported_languages: Language[];
  voice_persona: VoicePersona;
  verify_address: boolean;
  max_call_seconds: number;
  silence_hangup_secs: number;
  active: boolean;
  plan: string;
  widget_enabled: boolean;
  widget_key: string;
  widget_settings: WidgetSettings;
  webhook_url: string;
  webhook_secret: string;
  /** Next scheduled "call everyone" run (ISO UTC), or null. */
  auto_call_at: string | null;
  auto_call_repeat_daily: boolean;
  /** Add-ons on top of the plan: {key: quantity}. */
  addons: Record<string, number>;
  channels: ChannelSetup;
  created_at: string;
};

export type ChannelSetup = {
  whatsapp: { number: string };
  messenger: { page_id: string; page_name: string; connected: boolean };
};

export type MerchantSettingsInput = Partial<{
  business_name: string;
  owner_name: string;
  phone: string;
  email: string;
  support_phone: string;
  custom_greeting: string;
  knowledge: string;
  vertical_config: Record<string, unknown>;
  timezone: string;
  currency: string;
  emergency_number: string;
  language: Language;
  supported_languages: Language[];
  voice_persona: VoicePersona;
  verify_address: boolean;
  max_call_seconds: number;
  silence_hangup_secs: number;
  widget_enabled: boolean;
  widget_settings: WidgetSettings;
  webhook_url: string;
}>;

/** Everything the portal renders itself from (GET /api/auth/workspace). */
export type Workspace = {
  merchant: Merchant;
  vertical: VerticalSpec;
  /** The account's vertical settings merged over the vertical's defaults. */
  config: Record<string, unknown>;
  regions: Region[];
  usage: Usage;
  entitlements: Entitlements;
  public_base_url: string;
  telephony: { twilio_configured: boolean; platform_number: string };
};

/** A record: an order, appointment, lead, booking or message. */
export type Order = {
  id: string;
  merchant_id: string;
  kind: string;
  source: string;
  order_ref: string | null;
  customer_name: string;
  customer_phone: string;
  address: string | null;
  items_summary: string | null;
  total_amount: string;
  currency: string;
  status: OrderStatus;
  notes: string | null;
  catalog_item_id: string | null;
  catalog_item_name: string;
  scheduled_at: string | null;
  details: Record<string, unknown>;
  /** One-line, vertical-specific description. */
  summary: string;
  flow_data: Record<string, unknown>;
  call_attempts: number;
  last_call_at: string | null;
  created_at: string;
  /** Present on admin listings only. */
  merchant_name?: string;
};

/** Record form values: columns top-level, vertical fields top-level or under `details`. */
export type OrderInput = {
  customer_name: string;
  customer_phone: string;
  order_ref?: string;
  address?: string;
  items_summary?: string;
  total_amount?: string;
  notes?: string;
  scheduled_at?: string | null;
  catalog_item_id?: string | null;
  details?: Record<string, unknown>;
  [key: string]: unknown;
};

export type OrderUpdate = Partial<OrderInput> & { status?: OrderStatus };

export type CallLog = {
  id: string;
  order_id: string | null;
  direction: CallChannel;
  flow: string;
  caller_number: string;
  twilio_call_sid: string | null;
  recording_sid: string | null;
  call_status: string | null;
  outcome: string | null;
  transcript: string | null;
  language: string | null;
  duration_secs: number | null;
  final_node: string | null;
  llm_prompt_tokens: number;
  llm_cached_tokens: number;
  llm_completion_tokens: number;
  tts_chars: number;
  tts_cache_hits: number;
  created_at: string;
  customer_name?: string;
  /** Present on admin listings only. */
  merchant_id?: string;
  merchant_name?: string;
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

export type CatalogItem = {
  id: string;
  kind: string;
  name: string;
  data: Record<string, unknown>;
  active: boolean;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
};

export type CatalogItemInput = {
  name?: string;
  data?: Record<string, unknown>;
  active?: boolean;
  sort_order?: number;
};

export type CatalogImportResult = { created: number; skipped: number; errors: string[] };

export type FlowPreview = { steps: string[]; sections: Partial<Record<Direction, string[]>> };

/** Test console. */
export type TestCallInput = { direction: Direction; record_id?: string | null; caller_number?: string };
export type TestCallTicket = {
  call_log_id: string;
  /** The record of an outbound test call ("" for inbound). */
  order_id: string;
  media_token: string;
  /** Public wss:// media URL when the server has one; local dev connects to :8000 directly. */
  ws_url: string | null;
  stream_sid: string;
};
export type AgentState = {
  stage: string;
  node: string;
  slots: Record<string, unknown>;
  outcome: string;
  record_id: string;
  ended?: boolean;
};
export type ChatStart = { session_id: string; messages: string[]; state: AgentState };
export type ChatReply = { messages: string[]; ended: boolean; state: AgentState };

export type AdminOverview = {
  merchants: number;
  active_merchants: number;
  orders: number;
  calls_today: number;
  confirmed_today: number;
  cancelled_today: number;
  orders_today: number;
  pending_orders: number;
  calling_orders: number;
  needs_review_orders: number;
  inbound_today: number;
  booked_today: number;
  by_vertical: Record<string, number>;
  pending_addon_requests: number;
};

export type AdminMeta = {
  verticals: VerticalSpec[];
  regions: Region[];
  plans: Plan[];
  languages: { code: Language; label: string }[];
};

export type AdminMerchantDetail = {
  merchant: Merchant;
  usage: Usage;
  entitlements: Entitlements;
  addon_requests: AdminAddonRequest[];
  catalog_items: number;
  records: number;
};

export type MerchantCreateInput = {
  business_name: string;
  username: string;
  password: string;
  vertical: VerticalKey;
  region: string;
  language: Language;
  plan?: string;
  owner_name?: string;
  phone?: string;
  email?: string;
  support_phone?: string;
  inbound_number?: string;
  voice_persona?: VoicePersona;
  timezone?: string;
  currency?: string;
  emergency_number?: string;
};

export type MerchantAdminUpdate = MerchantSettingsInput &
  Partial<{ password: string; active: boolean; plan: string; region: string; inbound_number: string; whatsapp_number: string }>;

export type SalesInquiryStatus = "new" | "contacted" | "demo" | "won" | "lost";

export type SalesInquiry = {
  id: string;
  name: string;
  email: string;
  phone: string;
  company: string;
  business_type: string;
  country: string;
  monthly_calls: string;
  message: string;
  status: SalesInquiryStatus;
  admin_notes: string;
  created_at: string;
};

export type SalesInquiryInput = {
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  business_type?: string;
  country?: string;
  monthly_calls?: string;
  message?: string;
  /** Honeypot — leave empty. */
  website?: string;
};

/** Public website data. */
export type PublicCatalog = {
  verticals: { key: VerticalKey; label: Label; description: Label; directions: Direction[] }[];
  plans: Plan[];
  addons: AddonItem[];
  regions: Region[];
  /** Widget key of the demo account (empty when no demo is configured). */
  demo_widget_key: string;
};

export type BulkCallRunState = "queued" | "running" | "done" | "cancelled" | "failed";

export type BulkCallRun = {
  id: string;
  state: BulkCallRunState;
  source: "manual" | "scheduled";
  total: number;
  started: number;
  failed: number;
  skipped: number;
  error: string;
  created_at: string | null;
  finished_at: string | null;
};

export type AutoCallSchedule = {
  at: string | null;
  repeat_daily: boolean;
};

export type BulkCallStatus = {
  /** Records a "Call all" would dial right now. */
  eligible: number;
  max_concurrent: number;
  max_attempts: number;
  run: BulkCallRun | null;
  schedule: AutoCallSchedule;
};

export function bulkRunActive(run: BulkCallRun | null | undefined): boolean {
  return run?.state === "queued" || run?.state === "running";
}

/** Statuses in which a new call must not be placed. */
export function callLocked(status: OrderStatus | string, kind = "order"): boolean {
  if (status === "calling") return true;
  if (status === "cancelled") return true;
  return kind === "order" && status === "confirmed";
}

// ------------------------------------------------------------------ SMS + calendar sync

export type SmsSettings = {
  enabled: boolean;
  /** Text the caller when the agent books / takes their details. */
  on_booking: boolean;
  /** Text when a booking is moved or cancelled. */
  on_change: boolean;
  /** Reminder text this many hours before; 0 = no reminder. */
  reminder_hours: number;
};

export type CalendarItem = {
  id: string;
  name: string;
  /** This doctor / agent / team's own feed of bookings. */
  feed_url: string;
  /** Their busy calendar (iCal link) — times there are never offered. */
  calendar_ics: string;
  google_calendar_id: string;
};

export type GoogleCalendarState = {
  /** The server has GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET. */
  available: boolean;
  /** The plan (or an add-on) includes two-way Google sync. */
  included: boolean;
  connected: boolean;
  email: string;
  calendar_id: string;
  check_busy: boolean;
  redirect_uri: string;
};

export type Integrations = {
  sms: {
    settings: SmsSettings;
    /** Twilio is configured with a sender on this server. */
    platform_ready: boolean;
    sender: string;
    sent_this_month: number;
  };
  calendar: {
    feed_url: string;
    /** The feed URL is reachable from the internet (PUBLIC_BASE_URL set). */
    public: boolean;
    busy_ics_urls: string[];
    items: CalendarItem[];
    google: GoogleCalendarState;
  };
};

export type SmsMessage = {
  id: string;
  order_id: string | null;
  kind: string;
  to_number: string;
  body: string;
  status: "queued" | "sent" | "delivered" | "failed" | "undelivered" | "skipped" | string;
  error: string;
  segments: number;
  created_at: string;
};

export type CalendarCheck = { ok: true; busy_count: number; next: [string, string][] } | { ok: false; error: string };

export type GoogleCalendarOption = { id: string; name: string; primary: boolean };

// ------------------------------------------------------------------ add-ons + channels

/** What the account may use: plan + add-ons. */
export type Entitlements = {
  plan: string;
  product: "voice" | "chat";
  channels: ChannelKey[];
  features: string[];
  addons: Record<string, number>;
  limits: Limits;
};

export type AddonCategory = "channel" | "capacity" | "feature" | "service";

export type AddonItem = {
  key: string;
  name: string;
  category: AddonCategory;
  price: number;
  period: "month" | "once";
  /** "$29 / mo", "$299 once" */
  price_label: string;
  summary: string;
  /** Can be bought more than once (minute packs, numbers). */
  stackable: boolean;
  channel: ChannelKey | "";
  feature: string;
  /** Per unit, e.g. {minutes: 100}. */
  grants: Record<string, number>;
  products: string[];
};

export type AddonRequestStatus = "pending" | "approved" | "declined" | "cancelled";

export type AddonRequest = {
  id: string;
  addon: string;
  quantity: number;
  note: string;
  status: AddonRequestStatus;
  admin_note: string;
  created_at: string;
  decided_at: string | null;
};

export type AdminAddonRequest = AddonRequest & {
  merchant_id: string;
  merchant_name: string;
  merchant_plan: string;
  addon_name: string;
  price_label: string;
};

/** GET /api/addons */
export type AddonShop = {
  catalog: AddonItem[];
  /** Keys this account may still request. */
  available: string[];
  entitlements: Entitlements;
  plan: Plan;
  requests: AddonRequest[];
};

/** GET /api/channels */
export type ChannelsView = ChannelSetup & {
  active: ChannelKey[];
  platform: { whatsapp_ready: boolean; whatsapp_webhook: string; messenger_ready: boolean; messenger_webhook: string };
};
