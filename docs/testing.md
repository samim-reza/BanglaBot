# Testing BanglaBot v2 for free

Everything below runs on free tiers or on your laptop. Nothing here needs a credit card.

## 1. One-time setup

1. **Keys already in `.env`:** Telnyx (new key), Groq, Gemini, the local speech server key.
2. **Still to add (2 minutes each):**
   - **Deepgram** ($200 free credit, best streaming STT for phone audio): sign up at
     <https://console.deepgram.com/signup> → API Keys → create → put it in `.env` as `DEEPGRAM_API_KEY=`.
   - **Supabase shared audio cache** (optional): Supabase → project *banglabot* → Project Settings →
     API Keys → *New secret key* → `.env` `SUPABASE_SECRET_KEY=`. Without it the cache still works on
     memory + disk; it just doesn't survive Render redeploys.
3. **Database:** the first boot adds the new tables/columns automatically (admin users, audit log,
   agent-flow settings, payments, usage ledger, subscriptions). Stop the Render service first if you
   boot locally against the same Supabase database — two copies would both run the schedulers.

## 2. Start everything locally

```bash
./scripts/dev.sh --speech --route-telnyx
```

- `--speech` starts the open-source speech server on your GPU (Parakeet STT + Kokoro TTS; first run
  downloads ~2 GB; log in `/tmp/banglabot-speech.log`).
- `--route-telnyx` points +1 872 342 8160 at your ngrok URL (signed webhook) and back to production
  when you stop the script.
- Without `--speech`, calls use the free cloud chain (Deepgram/Groq for STT, Gemini/edge for TTS).

Open:

| What | Where |
|---|---|
| Website / owner sign-in | <http://localhost:3000> → /login |
| Admin panel | <http://localhost:3000/admin> (first boot seeds a superadmin from `ADMIN_USERNAME` / `ADMIN_PASSWORD`) |
| API docs | <http://localhost:8000/docs> |

## 3. Try a vertical without a phone (simulator, free LLM, no database)

```bash
cd backend
venv/bin/python -m scripts.simulate clinic --say "Hi, I'm a new patient, I'd like the heart doctor on Monday around 2" --say "Karim Hossain" --say "yes"
venv/bin/python -m scripts.simulate restaurant --say "two large pepperoni pizzas for delivery" --interactive
venv/bin/python -m scripts.simulate salon --chat --interactive
```

Each turn prints the tool call, which model served it, latency and prompt tokens.
Free Groq limits ≈ 8K tokens/minute per model — if you see fallbacks to Gemini, wait a minute.

## 4. Call the number

1. Create an account in the admin panel (Accounts → New) — pick the business type (clinic, dental,
   vet, restaurant, salon, real estate, home service, ecommerce, custom) and set its inbound number
   to `+18723428160`.
2. Sign in as that owner, add the catalog (doctors / menu / services), then open **Agent** to shape
   the call: switch steps on/off, reorder, reword any line, set payment (pay on arrival / caller's
   choice / online required), approval, intake fields and custom questions. **Save** pre-generates
   all fixed lines into the audio cache.
3. Call +1 872 342 8160 from your phone. Things to try:
   - Say several details at once ("I'm new, Dr Rahman tomorrow at 5, my name is …") — those
     questions are skipped.
   - Ask a question mid-booking ("do you take Aetna?") — it answers and returns to the step.
   - Change your mind at the read-back ("make it Tuesday") — it re-reads the summary.
   - Say "chest pain" — the emergency line plays immediately.
4. Watch it live: Admin → **Live calls** (stage, model, STT provider; hang-up button).

## 5. Payments (test mode)

Turn on Payment → "Online payment required" in the Agent page (or lock it from the admin account
page). After a booking, the record shows *payment pending* with a link to the dummy pay page
(`/pay/<token>`); "Pay (test)" marks it paid. SMS delivery needs the Telnyx account upgraded — until
then the link is shown in the portal.

## 6. What to look at in the admin panel

- **Voice engine:** which LLM/STT/TTS provider is serving, free quota left per model, cache hit
  rate, local speech server status, test buttons.
- **Finance:** cost of every call by provider/model (free tiers show $0 plus the list-price shadow
  cost), revenue, margin, cache savings.
- **Accounts → Call flow:** the owner's flow, with locks (e.g. force online payment).
- **Audit log**, **Admins** (roles, 2FA), **System** health.

## 7. Automated checks (no database, no app start)

```bash
cd backend && venv/bin/python -m pytest -q        # pure unit tests
cd frontend && npx tsc --noEmit && npm run build   # type check + static build
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Call connects but silence | Admin → Voice engine: is any TTS provider ready? Is the speech server up (`curl localhost:8100/health`)? |
| "All LLM providers failed" | Free quota exhausted — wait a minute, or add another key / set `LLM_ALLOW_PAID=true` with an OpenAI key |
| Number still rings production | Run `cd backend && venv/bin/python -m scripts.telnyx_route local --url https://<ngrok>` |
| Production won't boot | Set `ADMIN_TOKEN_SECRET` (32+ chars), `ADMIN_PASSWORD` (10+), `ENCRYPTION_SECRET` (32+) on Render |
