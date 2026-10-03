# BanglaBot — AI voice & chat agents for small businesses

One platform, four ready-made agents. Each account runs one **business engine**, chosen by the admin when the account is created:

| Engine | Inbound: the customer calls or chats | Outbound: the business calls |
|---|---|---|
| **Clinic** (`clinic`) | Books doctor appointments from the doctor list (days, hours, minutes per patient, fee); moves or cancels the caller's appointments, found by phone number; answers from the knowledge base; emergencies get the local emergency number | Reminder calls: confirm, reschedule or cancel |
| **Real estate** (`real_estate`) | Qualifies buyers, renters and sellers; presents fitting listings; books viewings; scores leads hot / warm / cold in code | Lead follow-up calls |
| **Home services** (`home_service`) | Takes the job (service, problem, address), checks the service area, books an arrival window with the call-out charge and price range; safety line for gas, sparks or fire | Visit confirmation calls |
| **E-commerce** (`ecommerce`) | Reception: answers from the knowledge base, takes a message | Cash-on-delivery order confirmation calls |

Every engine also gets (some as add-ons — a plan is one product with limits, extras are bought on top):
- the same agent as a **website chat widget** (one script tag), a **WhatsApp bot** (Twilio) and a **Messenger bot** (Facebook Page);
- **SMS confirmations and reminders**: a text after the agent books, when a booking moves or is cancelled, and a reminder before it;
- **calendar sync** for the scheduled engines: two-way Google Calendar (bookings are written there; busy times are never offered), a private iCal booking feed for Outlook / Apple / any app, and iCal busy links (also per doctor);
- **webhooks** into the business's own systems;
- **live transfer** to the business's team;
- **recordings and transcripts**;
- **bulk and scheduled outbound** calls;

Accounts are English by default (Bangla is supported). Each account has a **region preset** that sets time zone, currency, emergency number, phone format and English accent.

Pricing, unit economics and go-to-market: [docs/pricing.md](docs/pricing.md).

## Stack

- **Backend:** FastAPI + SQLAlchemy (async, PostgreSQL); optional Redis; Telnyx TeXML (inbound + outbound calls, bidirectional media streaming) and Telnyx Messaging (SMS); Twilio only for WhatsApp.
- **Voice pipeline:** streaming speech-to-text (`gpt-4o-mini-transcribe`) → `gpt-5.4-mini` with flow tools → Azure neural text-to-speech (μ-law 8 kHz) behind an in-memory + disk LRU voice cache.
- **Frontend:** Next.js (app router) + Tailwind. It serves the marketing website, the account portal and the admin console.

## How the engine works

```
backend/app/
  flows/        THE MAIN ENGINE — pure conversation logic, no I/O
    base.py       Flow contract, outcomes, CommitAction / CommitResult, identity gate
    context.py    CallContext: account, record, caller, catalog snapshot, booked slots, local clock
    runtime.py    per-call slot store; the current stage is DERIVED from the slots
    steps.py      shared slot-filling machinery: yes/no fast paths, read-back → commit, amend
    scheduling.py sessions, slots, serials, capacity, nearest-slot picking
    timefmt.py    dates/times as callers say and hear them (en + bn)
    hearing.py    did the caller's own words support a yes / no / cancel?
  verticals/    BUSINESS ENGINES plugged into the main engine
    ecommerce.py clinic.py real_estate.py home_service.py reception.py
    base.py       Vertical spec: flows per direction, record/catalog/config field specs, labels
    forms.py      validates portal input against those field specs
  voice/        TRANSPORTS + speech
    agent.py      CallAgent: the conversation brain (model loop, tools, fast paths)
    bridge.py     audio transport (Telnyx media stream, or the browser test call)
    text_session.py  text transport (portal chat test, website widget)
    tools.py      save_details / terminals / transfer / end_call; commits through a CallStore
    prompts.py    layered prompt: core rules → engine rules → business → this call
    llm.py stt.py tts.py tts_cache.py audio.py languages.py prepared.py twiml.py
  services/     call lifecycle (call_service), context loading, catalog, records, usage, webhooks, dialer
  api/routes/   auth (owner), orders (records), catalog, calls, agent (tests), admin, public, telnyx (calls + SMS), twilio (WhatsApp)
```

**One model round-trip per caller turn.**
1. The model calls `save_details` with whatever the caller said, plus an optional one-sentence `reply` to a side question.
2. The backend validates and resolves the details: doctor names to the doctor list, dates against the doctor's schedule.
3. It derives the next stage and speaks the next question itself, from the voice cache when the line is fixed.
4. Clean yes/no answers on scripted steps (read-backs, reminders, identity checks) skip the model entirely.
5. When everything is confirmed, the backend writes the result: it re-checks capacity under a Postgres advisory lock, so two callers can't take the last slot.

**Prompt caching.** The prompt is built most-stable-first (core rules, then engine rules, then the business, then this call). Step changes are appended at the end of the conversation, so the prefix stays identical and OpenAI caches it; test calls hit 75–85% cached tokens.

## Running locally

```bash
cp .env.example .env   # fill OPENAI_API_KEY, AZURE_SPEECH_KEY/REGION, TELNYX_*, DATABASE_URL
./scripts/dev.sh       # uv venv, ngrok, backend :8000, frontend :3000
```

- **First start:** creates or extends the schema with idempotent patches. No demo data is created: add accounts in the admin console (or `python -m scripts.create_merchant`).
- **Admin console:** `/admin`, log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
- **Website:** `/`. Owner portal: `/login`.

**Running an agent:**
- **Inbound calls:** in the admin console, set an account's *inbound number* to a Telnyx number. The number belongs to the TeXML application `TELNYX_TEXML_APP_ID`, whose voice webhook is `{PUBLIC_BASE_URL}/telnyx/inbound` (POST); `TELNYX_AUTO_CONFIGURE_INBOUND=true` sets it on startup. Calls to a number no account has claimed are answered "not in service".
- **Try it:** call the account's number from your phone; preview the website chat on the portal's Channels page. Every conversation lands in *Calls & chats* with its transcript.
- **SMS:** with `TELNYX_API_KEY` set, texts go out from `TELNYX_SMS_FROM` or the calling number, which must be on the messaging profile `TELNYX_MESSAGING_PROFILE_ID` (US local numbers also need 10DLC registration). Each account switches texts on in *Settings → Notifications* and can send itself a test. Delivery receipts need a public `PUBLIC_BASE_URL`.
- **Google Calendar:** create an OAuth web client (enable the Google Calendar API), set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, and register `{PUBLIC_BASE_URL or http://localhost:8000}/api/integrations/google/callback` as a redirect URI. Then use *Settings → Calendar → Connect Google Calendar*. While the OAuth app is in "Testing", add your Google account as a test user.
- **Plans and add-ons:** `backend/app/core/plans.py` (Chat agent; voice Starter / Growth / Pro) and `backend/app/core/addons.py` (catalog + `entitlements()` = what an account may use). Owners request add-ons on the portal's Add-ons page; the admin approves them (Admin → Requests) or edits an account's add-ons directly.
- **WhatsApp / Messenger:** see the "Chat channels" block in `.env.example`. Both run the same agent as the website chat (`app/services/channel_service.py`).
- **Jev (optional):** set `TYPESAFE_API_KEY` to settle natural yes/no answers on scripted steps without a full LLM turn (`app/voice/jev.py`); cancellations always need the caller's own words.
- **Terminal (real model, no database):** `cd backend && venv/bin/python -m scripts.simulate clinic`. Add `--say "..."` for scripted turns, `--direction outbound --record 0` for a reminder call, `--chat` for widget style.

## Hosting (free tier)

| Part | Where | Address |
|---|---|---|
| Website + portal + admin | Vercel (Hobby), root directory `frontend`, env `NEXT_BACKEND_URL=https://banglabot-api.onrender.com` | https://www.banglabot.xyz |
| Backend (FastAPI, calls, jobs) | Render free web service `banglabot-api`, Docker `backend/Dockerfile`, health check `/health`, Singapore | https://api.banglabot.xyz (also https://banglabot-api.onrender.com) |
| Database | Supabase session pooler (Singapore) | `DATABASE_URL` |
| DNS | cPanel zone `banglabot.xyz`: `@` A → Vercel, `www` CNAME → Vercel, `api` CNAME → Render; email `MX`/`mail` point at the cPanel server | |
| Keep-awake | `.github/workflows/keep-awake.yml` pings `/health` every 10 minutes (Render free sleeps after 15 idle minutes) | |

- Backend secrets live in Render → Environment (never in git). `PUBLIC_BASE_URL` is the Render address (Telnyx webhooks, calendar feeds); `FRONTEND_ORIGIN` lists the site origins (the first one is used for redirects); `TELNYX_AUTO_CONFIGURE_INBOUND=true` points the TeXML application at the hosted backend on every start.
- Both Render and Vercel redeploy on every push to `main`.
- The hosted backend and a local `./scripts/dev.sh` share the Supabase database, and both run the scheduled jobs: don't run them at the same time, or auto-calls and SMS reminders can go out twice. Incoming calls to the Twilio number go to the hosted backend; outbound calls from a local run still work through ngrok.
- `deploy/docker-compose.yml` + `deploy/Caddyfile` run the whole stack on any single server (VPS) instead.

## Tests

```bash
cd backend && venv/bin/python -m pytest -q    # pure unit tests: engines, tools, bridge with fakes — no database, no network
cd frontend && npx tsc --noEmit
```
