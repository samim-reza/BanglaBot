# Before production: what to buy and switch on

*Written 2026-10-16 from what Callisa actually uses today. Prices are approximate list prices
(±20 %); re-check each one before you pay. Per-minute call costs are worked out in
[capacity.md](capacity.md).*

Right now the whole platform runs on free tiers and trial credit. That's fine for testing, but
several of those tiers stop working, or aren't allowed, once real customers call.

## Do these first (in this order)

1. **Telnyx → Paid.** The trial number is **taken back around 2026-11-02**, and until then only your
   verified phone can call it.
2. **Render → a paid instance.** The free one sleeps, and the first call after a quiet spell fails.
3. **Supabase → Pro.** The free database pauses after a week without activity and has no backups.
4. **OpenAI credits**, then switch on paid models (see §5). Free models handle only a few dozen
   calls a day.
5. **Vercel → Pro.** The free plan doesn't allow commercial use.
6. **Email provider.** Signup and password-reset emails don't send yet.
7. **Telnyx SMS registration (10DLC).** Booking confirmations and reminders are blocked until then.

---

## 1. Fixed monthly services (must buy)

| # | Service | What Callisa uses it for | Today | What to buy | Approx. cost |
|---|---|---|---|---|---|
| 1 | **Telnyx** | Phone number, inbound/outbound calls | Trial: $5 credit, only your verified phone can call, 10-min calls, number reclaimed ~2 Nov | Upgrade to **Paid** (card payment, service address, 2FA, verified phone), then pre-pay credit | Number ≈ $1/mo + usage (§2) |
| 2 | **Telnyx SMS (US 10DLC)** | Booking confirmations, reminders | Blocked on trial | Register a brand + campaign, then attach the number to the messaging profile | ≈ $20 one-time, ≈ $2–10/mo + per-message fees |
| 3 | **Render** | Backend API + live voice calls | Free: sleeps after 15 min idle, ~50 s wake-up, so calls fail | **Standard** (2 GB) recommended; **Starter** (512 MB) is the bare minimum | $25/mo (Starter $7/mo) |
| 4 | **Supabase** | Database + shared audio cache bucket | Free: pauses after 7 days idle, 500 MB, no backups | **Pro** | $25/mo |
| 5 | **Vercel** | Website, owner portal, admin panel | Hobby: personal, non-commercial use only | **Pro** | $20/mo per member |
| 6 | **Domain** banglabot.xyz | Website + API address | Registered | Keep it renewed | ≈ $10–15/yr |

## 2. Pay-per-use services (move off free tiers)

| Service | What it does in a call | Today | Production | Approx. price |
|---|---|---|---|---|
| **OpenAI** gpt-5.4-mini | The agent's "brain" (LLM) | Key set, but paid models are switched off. Calls run on free Groq/Gemini | Buy pre-paid credits and put it first in the chain | ≈ $0.002–0.004 per call-minute |
| **Groq** (optional) | Fast backup LLM | Free tier (~200K tokens/day per model) | Developer tier, pay as you go | Low |
| **Gemini** (optional) | Backup LLM + backup voice | Free tier | Turn on billing in AI Studio | Low |
| **Deepgram** | Speech-to-text (Nova-3) + English voice (Aura-2) | $200 free credit | Pay as you go when the credit runs out | STT ≈ $0.005–0.008/min; voice $0.030 per 1K characters (≈40 % comes free from the cache) |
| **Azure Speech** | Backup English voice | Key set; check the tier (F0 free = 0.5M characters/month) | **S0** pay as you go | ≈ $15–16 per 1M characters |
| **Telnyx usage** | Call minutes + audio streaming, SMS | Trial credit | Paid account balance | ≈ $0.010 per call-minute; SMS ≈ $0.004/segment + carrier fees |

**All in, a call costs ≈ $0.025–0.03 per minute**, so ≈ $0.07 for a typical 2–3 minute booking call.

## 3. Needed for features you sell (free or cheap, but must be set up)

| Feature | Service | Status | What to do | Cost |
|---|---|---|---|---|
| Signup verification, password reset, notifications | **Email (SMTP)** | Not configured | Brevo (300 emails/day free) or Resend (3,000/month free). Fill in `SMTP_*` | Free → ≈ $20/mo at volume |
| Plans, add-ons, self-serve checkout | **Stripe** | Dummy payment page | Stripe doesn't accept Bangladesh-registered businesses. Options: a US company via Stripe Atlas (≈ $500 one-time), or Paddle / Lemon Squeezy as merchant of record (≈ 5 % + 50¢ per sale, needs a new adapter) | Per-sale fees (Stripe US: 2.9 % + 30¢) |
| Callers paying deposits to a business | The business's own payment link | Built in (`link` mode) | Each owner pastes their own link in the portal. No cost to you | Free |
| WhatsApp bot | **Twilio** (key set) or **Meta WhatsApp Cloud API** (built in) | Sandbox | Meta Business verification + an approved WhatsApp sender. Going direct on Cloud API avoids Twilio's fee | Twilio ≈ $0.005/msg + Meta per-conversation fees |
| Messenger / Instagram bots | **Meta app** | `META_APP_SECRET` not set | Create a Meta app; Business verification + App Review | Free |
| Google Calendar sync | **Google OAuth** | Not set locally | Google app verification for the calendar scope (needs privacy policy + terms pages, domain check; takes days to weeks). Until verified, users see "unverified app" and there's a 100-user cap | Free |
| Shared audio cache (no paying twice for the same sentence across servers) | **Supabase Storage** | Bucket exists, key missing | Add `SUPABASE_SECRET_KEY` | Included in Supabase |
| Rate limits and call counters across several servers | **Redis** | Off on Render (works fine with one server) | Upstash free tier, or Render Key Value when you run 2+ servers | Free → ≈ $10/mo |

## 4. Used for testing only: don't rely on these in production

| Thing | Why not | Replace with |
|---|---|---|
| **edge-tts** (free unofficial Microsoft Edge voices), currently in Render's `TTS_CHAIN` | Unofficial, can break or be blocked any day | Remove it from the chains (§5) |
| **Local speech server** (Parakeet + Kokoro on your laptop GPU) | Runs on your laptop only | Deepgram/Azure. Renting GPUs (~$350–550/mo each) only pays off past ~60–100K minutes/month |
| **Free Groq/Gemini tiers as the main LLM** | A few dozen calls per day | Keep them as backups behind OpenAI |
| **Test accounts** (`demo_*`, `platform_admin` in `backend/.test-accounts.txt`) | Shared test passwords | Delete them or change the passwords; create your real admin |
| **ngrok** (`scripts/dev.sh`) | Local development only | Nothing. Production uses api.banglabot.xyz |

## 5. Settings to change after buying (Render → banglabot-api → Environment)

| Setting | Now | Production |
|---|---|---|
| `LLM_ALLOW_PAID` | `false` | `true` |
| `LLM_CHAIN` | free models first | `openai:gpt-5.4-mini,groq:openai/gpt-oss-120b,gemini:gemini-3.1-flash-lite` |
| `TTS_CHAIN` | `deepgram,gemini,edge,azure` | `deepgram,azure,gemini` |
| `PROVIDER_DAILY_CAPS_USD` | empty (no cap) | e.g. `openai=10,deepgram=10,azure=5`, a safety net against runaway spend |
| `SMS_ENABLED` | off | `true` (after 10DLC is approved) |
| `PAYMENT_PROVIDER` | `dummy` | `stripe` + `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| `TELNYX_PUBLIC_KEY` | empty (blocked on trial) | Copy from Telnyx → API Keys → Public Key (adds Ed25519 checks). Unsigned `/telnyx/*` URLs are already refused in production: run `python -m scripts.telnyx_route prod` before deploying so the TeXML app and messaging profile use the signed URLs |
| `SMTP_*` | empty | Your email provider's details |
| `SUPABASE_SECRET_KEY` | empty | Supabase → Project settings → API keys |

## 6. If you sell to US clinics or dentists (patient data)

Patient details in calls, transcripts and bookings fall under **HIPAA**. Every vendor that touches
them must sign a BAA (business associate agreement): Telnyx, Deepgram, OpenAI, Azure, Supabase,
Render and Vercel. Several only offer one on higher plans (Supabase needs the Team plan, ≈ $599/mo,
plus an add-on), so price this in before selling the medical product in the US. Restaurants,
salons, vets, real estate and home services don't need it.

## 7. Rough totals

| | Amount |
|---|---|
| **Fixed monthly** | Render $25 + Supabase $25 + Vercel $20 + Telnyx number and 10DLC ≈ $5–12 + domain ≈ $1 + email $0 → **≈ $75–85/month** (≈ $55 with Render Starter) |
| **Usage** | ≈ $0.025–0.03 per call-minute → 1,000 minutes ≈ $25–30, 10,000 minutes ≈ $250–300 |
| **One-time** | Telnyx 10DLC ≈ $20; Stripe Atlas ≈ $500 only if you take the US-company route |

Check your **GitHub Student Developer Pack** for current cloud credits (for example Azure for
Students) before paying for Azure Speech.
