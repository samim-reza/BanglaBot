# BanglaBot — Cost Analysis & Pricing (BDT, per minute)

All figures at **৳123 / USD** (Aug 2026). Production stack: **local BD telephony
(Alap/BTCL/IPTSP) + ElevenLabs `eleven_v3` + OpenAI `gpt-5.4-mini` /
`gpt-4o-mini-transcribe`**. A typical confirmation call runs **1–1.5 minutes**.

## 1. Cost per connected minute

| Component | Rate | ৳ / minute |
|---|---|---:|
| **Telephony — option A: Twilio → BD** | $0.060/min + $0.0044/min media streams | ৳7.9 |
| **Telephony — option B: Alap (BTCL) / local IPTSP** | 40 paisa/min + 15% VAT, 1-sec pulse | **৳0.46** |
| ElevenLabs TTS (eleven_v3) | agent speaks ~320 chars ≈ 320 credits per call-minute (Creator: $22 / 121k credits) | ৳7.2 |
| OpenAI LLM (gpt-5.4-mini) | $0.75/M in, $4.50/M out | ৳0.7 |
| OpenAI STT (gpt-4o-mini-transcribe) | $0.003/min of user speech (~40% of the call) | ৳0.2 |
| **Total — Twilio stack** | | **≈ ৳16 /min** |
| **Total — Alap/local stack (production)** | | **≈ ৳8.6 /min** |

- **Billing granularity matters:** Twilio rounds up to whole minutes (a 70-second call
  bills 2 minutes → effective ~৳19/min on short calls). Alap's 1-second pulse bills
  exactly what you use.
- Unanswered calls cost ≈ nothing on either provider (answered time only).
- On the local stack, **ElevenLabs is ~84% of the per-minute cost** — trimming TTS
  (shorter script, cached greeting audio) is the main remaining lever.

### Caveats on the Alap/BTCL route

1. **The consumer Alap app can't be wired into this backend.** You need a business SIP
   trunk (BTCL IP Telephony, or an IPTSP like Amber IT / ADN / Link3 — similar
   ৳0.40–0.70/min rates), plus a SIP↔media bridge (Asterisk/FreeSWITCH) in front of the
   Pipecat pipeline — Pipecat's telephony serializers speak Twilio/Telnyx-style
   websockets, not raw SIP. Roughly 1–2 weeks of one-time engineering.
2. **Regulatory:** automated outbound calls from a +880 business number fall under BTRC
   telemarketing rules (caller-ID registration, calling-hour limits). Upside: a local
   +880 caller ID gets answered far more often than a foreign number.

## 2. Fixed monthly costs (production)

| Item | Plan | ৳ / month |
|---|---|---:|
| VPS (app + SIP bridge) | $18 | ৳2,214 |
| Supabase | $15 | ৳1,845 |
| ElevenLabs subscription | consumed per minute (see §1) | — |
| SIP trunk line rent | provider-dependent, usually small | ~৳500 (est.) |
| **Fixed base** | | **≈ ৳4,600** |

## 3. How many calls does a small F-commerce business actually need?

Reported numbers for Bangladeshi Facebook-page sellers: an established small page does
**~25 orders/day**; most smaller active pages do less, and only ~60k of the country's
2–2.5 lakh F-commerce pages generate regular sales
([The Daily Star](https://www.thedailystar.net/business/news/f-commerce-saviour-amid-pandemic-woes-2017061),
[TBS](https://www.tbsnews.net/economy/facebook-restriction-keeps-f-commerce-entrepreneurs-bay-905416)).

**Planning assumption: an average paying customer = 12 orders/day ≈ 360 orders/month
≈ 450 connected minutes/month** (1.25 min/call, ~85% answer rate — unanswered
redials cost ≈ nothing).

## 4. The business case: 10 customers

10 merchants × 360 orders/mo = **3,600 calls ≈ 4,500 connected minutes/month**.

| Cost item | Basis | ৳ / month |
|---|---|---:|
| Telephony (Alap/IPTSP) | 4,500 min × ৳0.46 | ৳2,070 |
| ElevenLabs | 1.44M credits → Scale plan $330 | ৳40,590 |
| OpenAI (LLM + STT) | 4,500 min × ৳0.9 | ৳4,050 |
| VPS + Supabase + trunk | §2 | ৳4,600 |
| **Total** | | **≈ ৳51,300** |

→ **৳11.4 per minute · ~৳14 per verified order** at this volume.

Revenue at the recommended pricing (§5): 10 merchants on the Business tier
= ৳130,000/month.

| | ৳ / month |
|---|---:|
| Revenue (10 × Business tier) | ৳130,000 |
| Costs | ৳51,300 |
| **Gross profit** | **≈ ৳78,700 (~60% margin)** |

With trimmed TTS (short script + cached greeting audio, ~40% fewer credits), costs drop
to ≈ ৳35,000 → **≈ ৳95,000/month profit**. On Twilio instead of local telephony, the
same book loses most of that: costs ≈ ৳87,000 → profit ≈ ৳43,000.

## 5. Recommended merchant pricing (per minute)

| Package | Price / mo | Included minutes | Effective ৳/min | Extra minutes |
|---|---:|---:|---:|---:|
| Trial | ৳0 | 25 (7 days) | — | — |
| Starter | ৳3,000 | 125 | ৳24 | ৳28 |
| Growth | ৳7,000 | 320 | ৳22 | ৳25 |
| **Business** (fits the avg. 450-min customer) | ৳13,000 | 650 | ৳20 | ৳22 |

- One order confirmation ≈ 1–1.5 minutes → quote merchants **"৳25–35 per verified
  order"** in sales talks while billing in minutes.
- No rollover of unused minutes; 15% off annual prepay.

**Sales benchmark:** a call-center employee (৳12,000–18,000/mo, ~2,500–3,000
talk-minutes) costs ৳5–7/min — cheaper on raw price, so don't sell on price. Sell on
**RTO losses**: unverified COD orders fail 20–35% of the time at ~৳100–160 courier cost
each. Verifying 100 orders (~125 min ≈ ৳2,750) that cuts RTO from ~25% to ~8% saves
~17 failed deliveries ≈ **৳1,700–2,700 in courier fees** plus freed inventory. The
sweet spot is exactly the 100–600 orders/mo shop: too small to hire a caller, too busy
to phone everyone.

## 6. Assumptions & sources

- Exchange rate ৳123/USD (mid-market, Aug 2026).
- Twilio → BD: $0.060/min + $0.0044/min media streams, per-minute rounding —
  [twilio.com/voice/pricing/bd](https://www.twilio.com/en-us/voice/pricing/bd).
- Alap (BTCL): 40 paisa/min + 15% VAT, 1-second pulse —
  [businessinspection.com.bd](https://businessinspection.com.bd/btcls-alaap-app-revolutionary-solution-for-affordable-calling/);
  IPTSP business trunks ৳0.40–0.70/min.
- OpenAI: gpt-5.4-mini $0.75/M input, $4.50/M output —
  [openrouter.ai](https://openrouter.ai/openai/gpt-5.4-mini);
  gpt-4o-mini-transcribe ≈ $0.003/min — [costgoat.com](https://costgoat.com/pricing/openai-transcription).
- ElevenLabs: Creator $22/mo = **121k credits** (own account); Pro $99/500k, Scale $330/2M;
  eleven_v3 ≈ 1 credit/character; agent speaks ~320 chars per call-minute.
  **Free plan can't be used** — API TTS with library voices requires a paid plan (verified: HTTP 402).
- F-commerce order volume: established small pages ~25 orders/day; planning assumption
  12 orders/day per paying customer —
  [thedailystar.net](https://www.thedailystar.net/business/news/f-commerce-saviour-amid-pandemic-woes-2017061),
  [tbsnews.net](https://www.tbsnews.net/economy/facebook-restriction-keeps-f-commerce-entrepreneurs-bay-905416).
- Not included: your own time, payment-gateway fees (~2–3%), marketing.
