# 📞 BanglaBot — বাংলায় অর্ডার কনফার্মেশন কল

A SaaS platform for Bangladeshi ecommerce businesses. Merchants sign up, enter their
orders; an AI voice agent calls the customer **in Bengali**, confirms (or cancels)
the order, and the result updates live on the dashboard. Subscriptions are metered
per call/minute, and a full platform-admin console manages merchants, plans,
billing, and support.

## Stack

| Piece | Choice |
|---|---|
| Backend | FastAPI + SQLAlchemy (async) |
| Database | Supabase Postgres (session pooler, `ap-northeast-2`) |
| Telephony | Twilio Programmable Voice + Media Streams |
| Voice pipeline | [Pipecat](https://github.com/pipecat-ai/pipecat) (open-source) |
| LLM | OpenAI `gpt-5.4-mini` (cheap, no realtime model) |
| STT | OpenAI `gpt-4o-mini-transcribe` (Bengali, ~$0.003/min) |
| TTS | ElevenLabs `eleven_v3` (Bengali; requires a paid ElevenLabs plan — the free plan blocks API TTS). Voice/model/key set in `backend/.env` |
| Frontend | Vite + React (light theme, Bengali UI) |

## SaaS features

**Public site**: a bilingual landing page at `/` (hero, how-it-works, features,
live pricing from the plan catalog, FAQ) with signup/login entry points. Every
screen — landing and app — has a **বাং/EN language toggle** (Bengali is the
default; the choice persists per browser).

**Call recordings**: every confirmation call is recorded via Twilio. Merchants
can replay a call from the order's call history; the platform admin can replay
any call from the admin call feed. Audio is streamed through the backend proxy
(`/api/orders/recordings/{log_id}`, `/api/admin/recordings/{log_id}`) — Twilio
credentials never reach the browser.

**Merchant side** (self-serve):
- **Signup with free trial** (`/signup`) — 14 days / 20 calls by default; toggleable
  by the platform admin.
- **Billing** (`/billing`) — current plan + status, usage meters (calls & minutes
  this period), plan upgrade (invoice issued as *due*; paid manually via bKash and
  confirmed by the admin), invoice history.
- **Support** (`/support`) — threaded tickets with the platform team.
- **Settings** (`/settings`) — business profile + password change.
- Quota enforcement: starting a confirmation call checks the subscription and
  monthly call/minute limits; over-limit or lapsed accounts get a Bengali 402
  message pointing at the billing page.

**Platform admin console** (`/admin`):
- **Dashboard** — MRR, active merchants, monthly call/minute totals, open tickets,
  due invoices, plan distribution, recent activity feed.
- **Merchants** — create/disable accounts, reset passwords, and manage each
  merchant's subscription: plan, status (trial/active/past-due/canceled), bonus
  call/minute quota, period extension, notes.
- **Plans** — edit the plan catalog (BDT price, call/minute limits, feature
  bullets, trial length, visibility). Seeded: ফ্রি ট্রায়াল / স্টার্টার ৳1,500 /
  গ্রোথ ৳4,000.
- **Billing** — invoice queue; generate period invoices, mark paid (bKash) or void;
  marking paid re-activates a past-due subscription.
- **Support** — ticket queue with threaded replies, status & priority.
- **Calls** — platform-wide call feed with outcomes, durations, transcripts.
- **Finance** — an automated cost engine modeled on a financial-intelligence
  design: every completed call is priced automatically (telephony / TTS / LLM /
  STT, per-minute BDT rates from [COSTS.md](COSTS.md)) into a `call_costs` row.
  The ফাইন্যান্স tab shows monthly revenue (MRR, collected, outstanding) vs
  cost with a daily-cost chart, component breakdown, per-merchant
  profitability, a what-if projector, and an editable **date-versioned rate
  table** (changes apply to new calls only; history is never repriced).
- **Team** — additional platform-admin accounts (last admin is undeletable).
- **Logs** — append-only audit trail (logins, signups, plan changes, invoices,
  entitlement denials, settings edits…).
- **Settings** — platform name, support contacts, bKash payment number, signup
  on/off, trial plan, entitlement mode (`enforce` blocks calls, `observe` only logs).

## Run locally

```bash
# one-time: auth ngrok if you haven't
ngrok config add-authtoken <your-token>

./scripts/dev.sh
```

The script starts ngrok, injects the public URL into the backend
(`PUBLIC_BASE_URL`), and starts backend (`:8000`) + frontend (`:5173`).

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Platform admin login: **admin / admin123** (change via `ADMIN_PASSWORD` in `backend/.env`)

First steps: sign up a merchant from **/signup** (starts on the free trial), or log
in as admin → create a merchant (set the **support number** — the customer is
transferred there if they ask for a real person) → log in as that merchant → add an
order → press **📞 কল করুন**.

## What you must do on the Twilio side

1. **Nothing for inbound webhooks** — this app only makes *outbound* calls, and it
   passes the TwiML URL (`{PUBLIC_BASE_URL}/twilio/twiml/{order_id}`) per call via
   the REST API. You do **not** need to configure the phone number's webhook.
2. **Enable Bangladesh geo permissions** (required, calls will fail without it):
   Twilio Console → **Voice → Settings → Geo permissions** → enable **Bangladesh (+880)**.
3. **Trial account limits**: if the account is on trial, you can only call
   **verified numbers**. Verify your test number under
   **Phone Numbers → Verified Caller IDs**, or upgrade the account.
4. Ensure the account has balance — calls to BD mobiles cost roughly $0.05–0.09/min.
5. Optional: raise the "Max call duration" nothing needed — the app already caps
   calls at 4 minutes (`MAX_CALL_SECONDS`).
6. **Recordings need no console setup** — the app requests them per call via the
   REST API. Note Twilio bills recording storage (~$0.0005/min-month); prune old
   recordings from the Twilio console if that ever matters.

## How a call works

```
merchant clicks call → POST /api/orders/{id}/call
  → entitlement gate: subscription active? monthly call/minute quota left?
  → Twilio REST: create call (status + recording callbacks registered, record=true)
  → customer answers → Twilio fetches POST /twilio/twiml/{order_id}
  → TwiML <Connect><Stream> → WS /twilio/ws (μ-law 8kHz audio)
  → Pipecat pipeline: STT (bn) → gpt-5.4-mini (+tools) → TTS (bn)
  → tools write outcome to DB: confirm_order / cancel_order /
    transfer_to_human (dials merchant support number) / end_call
  → transcript saved on hangup; UI polls and updates
```

Order statuses: `pending → calling → confirmed / cancelled / no_answer / needs_review`.

## Project layout

```
backend/app
├── core/       config, security (JWT, bcrypt)
├── db/         async session (Supabase), bootstrap/seed/migrate
├── models/     merchants, orders, call_logs, platform_admins,
│               plans, subscriptions, invoices, support, audit, platform_settings
├── schemas/    pydantic I/O models (incl. pagination Page[T])
├── api/routes/ auth (login/signup), orders, billing, support, public,
│               admin, admin_billing, admin_support, admin_platform,
│               twilio (webhooks + WS)
├── services/   order queries, Twilio call origination,
│               billing (plans/subs/usage/invoices), entitlement gate, audit
└── voice/      Pipecat agent: prompts (Bengali), tools, pipeline
frontend/src
├── api/        fetch client + types
├── components/ layout, status badge, pagination
└── pages/      login, signup, dashboard, orders, billing, support, settings,
                admin/* (dashboard, merchants, orders, calls, plans, billing,
                support, team, logs, settings)
```

## Cost & pricing

Full unit-economics analysis (per-call BDT costs, merchant pricing tiers, margin
levers): see [COSTS.md](COSTS.md).

## Cost notes

Per ~2-minute confirmation call: Twilio BD voice ≈ $0.10–0.18, STT+TTS+LLM ≈ $0.04.
To cut costs further, swap the STT/TTS services in `backend/app/voice/agent.py`
for any other Pipecat-supported provider — the rest of the app is unaffected.
