# BanglaBot — Order Confirmation Call Agent

An outbound AI phone agent for e-commerce merchants in Bangladesh. A merchant
enters an order in the portal (customer name, phone, address, items, amount)
and clicks **Call**. The backend places a Twilio call to the customer; the
agent greets them in **Bangla** (or English), checks it is speaking with the
right person, optionally verifies the delivery address, states the order
naturally and asks for a yes/no. The outcome — `confirmed`, `cancelled`,
`needs_review`, `no_answer` — lands on the order together with the call log
and transcript. A platform admin manages merchants.

Development-only repository: one `.env`, no production mode, no deploy scripts.

## Stack

- **Backend** — FastAPI + SQLAlchemy (async, PostgreSQL), optional Redis,
  Twilio Programmable Voice (outbound calls + Media Streams).
- **Voice cascade** (`backend/app/voice/`) — streaming STT
  (`gpt-4o-mini-transcribe` over OpenAI's transcription session) →
  `gpt-5.4-mini` (Chat Completions + tools, `reasoning_effort=none`) → Azure
  Speech TTS (μ-law 8 kHz straight to Twilio) behind a **disk LRU cache**
  (`voice/tts_cache.py`, keyed by voice + language + text, bounded by entries
  and bytes) so every repeated line — greeting, questions, closings — is
  synthesized once and replayed for free.
- **Frontend** — Next.js (app router) + Tailwind. Merchant portal + `/admin`.

## Layout

```
backend/app/
  main.py                  FastAPI app; lifespan creates the schema, applies patches, seeds demo data
  core/                    settings (.env), JWT/password security, redis, logging, email
  db/                      async engine/session, bootstrap (create_all + idempotent patches + seed)
  models/                  Merchant, Order (status enum), CallLog
  schemas/                 request/response models
  api/routes/              auth (merchant), orders, admin, twilio (status/recording/media WS), public
  services/                order_service, call_service (Twilio outbound call, status callbacks, stale-call reconcile)
  flows/                   pure conversation logic: slot-derived node state machine, ecommerce flow, hearing policy
  voice/                   stt, llm, tts, tts_cache, languages, prompts, tools, bridge (per-call orchestrator), twiml
backend/scripts/           reset_database.py, create_merchant.py
backend/tests/             pure unit tests (flows, hearing, tools, bridge with fakes, tts cache) — no DB
frontend/app/              /, /login, /(merchant)/{dashboard,orders,orders/new,orders/[id],settings}, /admin/{login,merchants,orders,calls}
scripts/dev.sh             ngrok + backend + frontend launcher
.env.example               every setting the backend reads
docker-compose.yml         postgres + redis + backend + frontend
```

## Running locally

```bash
cp .env.example .env   # fill OPENAI_API_KEY, AZURE_SPEECH_KEY/REGION, TWILIO_*, DATABASE_URL
./scripts/dev.sh       # creates backend/venv with uv, starts ngrok, backend :8000, frontend :3000
```

`dev.sh` exports the ngrok https URL as `PUBLIC_BASE_URL` (Twilio must reach
`/twilio/*` and the `wss://…/twilio/media` stream), waits for `/health`, then
starts the frontend. Use `./scripts/dev.sh --no-ngrok` when you only need the
UI. First boot creates all tables on the configured database and — with
`AUTO_SEED_DEMO_DATA=true` — a demo merchant (`demo` / `demo123`) with sample
orders. Admin login uses `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`.

Manual alternative:

```bash
cd backend && ~/.local/bin/uv venv venv && ~/.local/bin/uv pip install --python venv/bin/python -r requirements-dev.txt
PUBLIC_BASE_URL=https://<your-tunnel> venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## How a call works

1. `POST /api/orders/{id}/call` → `call_service.start_confirmation_call` creates a
   `CallLog`, places the Twilio call with inline TwiML (`<Connect><Stream>` to
   `/twilio/media` carrying a signed media token), sets the order to `calling`.
2. On stream connect, `voice/bridge.py` speaks the greeting + "Am I speaking
   with {name}?" from the TTS cache, then runs the loop: caller audio → STT →
   `gpt-5.4-mini` with tools (`save_details`, `confirm_order`, `cancel_order`,
   `transfer_to_human`, `end_call`) → Azure TTS → Twilio.
3. The flow (`flows/ecommerce.py`) derives the current step from the collected
   slots: identity → (knows the customer? → relay / wrong number) → optional
   address check → decision. The backend owns the wording of each next
   question; a step change is appended as a system message.
4. `flows/hearing.py` only lets an outcome be written when the caller's own
   words support it (yes/no/later in Bangla or English); unclear answers are
   re-asked twice, then the order becomes `needs_review`.
5. `end_call` speaks the closing line and hangs up; Twilio's status callback
   (`/twilio/status/{order_id}`) settles `no_answer` / durations;
   `reconcile_stale_calls` fixes orders stuck in `calling` if a webhook is lost.

## Languages

Merchant settings choose the primary language (`bn` default or `en`), the
languages the agent also understands, and the voice persona (`female` =
Nabanita/Ava, `male` = Pradeep/Andrew). The agent follows the caller's language
when it is supported; amounts in BDT are spoken in Bangla words.

## Tests

```bash
cd backend && venv/bin/python -m pytest -q      # 47 pure unit tests, no database
cd frontend && npx tsc --noEmit
```
