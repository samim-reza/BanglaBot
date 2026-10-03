# Pricing, unit economics and go-to-market

*Prepared 3 October 2026. Prices checked against public list prices that day; items marked (unverified) could not be confirmed.*

## 1. What a minute costs us

Our call stack: Twilio Programmable Voice with a bidirectional media stream, OpenAI `gpt-4o-mini-transcribe` (speech-to-text), `gpt-5.4-mini` (the agent), Azure neural text-to-speech with our own voice cache.

| Item | Unit price | Per call-minute |
|---|---|---|
| Twilio inbound, US local number | $0.0085/min | $0.0085 |
| Twilio Media Streams | $0.0044/min | $0.0044 |
| Twilio recording + storage | $0.0025/min + $0.0005/min-month | $0.0030 |
| Speech-to-text (gpt-4o-mini-transcribe) | ~$0.003/min | $0.0030 |
| Agent model (gpt-5.4-mini: $0.75 / 1M input, $0.075 cached, $4.50 output) | ~3k-token prompt, 80% cached, ~60 output tokens per turn | ~$0.0030 |
| Text-to-speech (Azure neural, $15 / 1M characters) | ~500 characters of agent speech per call-minute | $0.0068 raw → **$0.0027 with our cache** |
| **Total, inbound US** | | **≈ $0.025/min** |

- Outbound to US/Canada mobiles adds $0.014/min and answering-machine detection $0.0075 per call. A 1.5-minute confirmation call costs about **$0.054**.
- The phone number is $1.15/month in the US. Planning cost, with 30% on top for infrastructure, retries and failed calls: **$0.04/min in the US and Canada, about $0.07/min for UK outbound.**
- A website chat (8 turns, text only) costs about **$0.01**.
- **Telephony is 55–95% of the cost.** Caching, plus answering yes/no steps without the model, keeps model and voice costs small; destination pricing is what moves margins.

Outbound to mobiles by country (Twilio list price per minute): US/CA $0.014, UK $0.0305, India $0.0496, Bangladesh $0.060, Australia $0.075, UAE $0.2995. Australia, India, Bangladesh and the UAE need minute multipliers or a local carrier (section 4).

How the product keeps cost and latency down (all built in):
- **Prompt caching.** The stable part of the prompt (rules, then the business's catalog) comes first. In test calls 75–85% of input tokens were served from cache.
- **One model round-trip per caller turn.** The model extracts the details; the backend speaks the next question itself, from the voice cache when the line is fixed.
- **Zero model calls on clean yes/no steps.** Read-back confirmations, reminders and identity checks skip the model.
- **Voice cache.** Fixed lines (greetings, questions, goodbyes) are synthesized once per voice and replayed from memory or disk.
- **Shared connection pool.** One keep-alive connection pool to OpenAI, warmed at startup.

## 2. What the market charges

| Type | Examples | Price |
|---|---|---|
| Developer voice platforms | Retell, Vapi, Bland, Synthflow | $0.07–0.31/min + build effort |
| Small-business AI receptionists | Rosie ($49/250 min), My AI Front Desk ($99/200 min), Dialzara ($29–349), Trillet ($49/150 min), Goodcall ($79–249) | $29–349/month |
| Vertical specialists | Weave (dental), Sameday (home services, $449/500 min), Structurely (real estate, ~$499 + setup) | $250–3,500/month + setup |
| Human answering | Ruby ($250 for 50 min ≈ $5/min), Smith.ai (~$10/call) | $3.45–5/min |
| A receptionist | US median $37,230/year (BLS) | ≈ $3,100/month in wages for one shift |

**Our position:** ready-made vertical agents (not a toolkit) at small-business prices. They answer and call out, include a website chat, and work in multiple regions. Our differentiators are outbound (reminders, follow-ups, cash-on-delivery confirmations) and price.

## 3. Our price list (live in `backend/app/core/plans.py` and on the website)

| Plan | Price | Minutes | Chats | Texts | Numbers | Overage | Our cost at full use | Gross margin |
|---|---|---|---|---|---|---|---|---|
| Starter | $49/mo | 150 | 100 | 100 | 1 | $0.30/min | ≈ $11 | ≈ 77% |
| Growth (featured) | $149/mo | 600 | 500 | 500 | 2 | $0.22/min | ≈ $44 | ≈ 70% |
| Pro | $349/mo | 1,800 | 2,000 | 2,000 | 3 | $0.16/min | ≈ $140 | ≈ 60% |
| Enterprise | from $999/mo | custom | — | custom | — | from $0.10/min | — | — |

- Free trial: 14 days, 50 minutes, 50 texts.
- **Texts (SMS).** A US text costs us about $0.011–0.013 all-in: Twilio's ≈ $0.0083 per segment plus 10DLC carrier fees. Check Twilio's current price list; these figures aren't verified. Full use of the included texts adds ≈ $1 / $6 / $24 a month. Real use is about one to two texts per booking, far below the cap. English templates stay within one 160-character GSM-7 segment. Bangla is Unicode, so each segment holds 70 characters and a text costs about double.
- **Calendar sync** costs us nothing per use. The Google Calendar API is free within quota, and iCal feeds are cached. Starter gets the feed and iCal busy links. Two-way Google sync is a Growth feature that drives upgrades.
- Annual billing: 2 months free.
- Unused minutes push blended margin to about 75%.

**Add-ons:**

| Add-on | Price |
|---|---|
| Extra number | $5/mo (US/CA), $10 (UK/AU) |
| Extra location or agent | $49/mo |
| Extra language | $19/mo |
| Chat-only plan | $29/mo for 500 conversations |
| 12-month recording retention | $10/mo |
| Extra texts | $10 per 500 (cost ≈ $6) |
| Done-for-you setup | $299 one-off |
| Cash-on-delivery confirmation | $0.20 per answered call (US/UK/CA) |

## 4. Regional pricing

| Region | Approach |
|---|---|
| US, Canada | List price in USD |
| UK, Australia | Price in local currency at parity, e.g. £39 / £119 / £279 and A$79 / A$229 / A$549. Outbound minutes count 1.5× (UK mobile) and 2.5× (AU mobile). |
| India, Bangladesh, Pakistan | 40–50% of list (Starter ≈ $22, Growth ≈ $65, Pro ≈ $149), **only once we route calls through a local carrier** (Exotel / Plivo / a Bangladeshi IPTSP at ≈ $0.01/min, unverified). Cash-on-delivery confirmation there sells at ₹3–8 / ৳8–10 per call, below our Twilio cost today. |
| UAE | List price; sell inbound and chat first. Twilio outbound there is about $0.30/min and VoIP is regulated. |

## 5. How we sell

Who to sell to first:
1. **Owner-run home-service businesses** in the US, CA, UK and AU: plumbers, electricians, HVAC, cleaners. They miss calls on job sites, and one booked job ($200–1,000) pays for a year of Starter.
2. **Private clinics** in the UK, UAE and South Asia, then US clinics once every provider in the chain has signed a HIPAA business associate agreement. The pitch: no more hold queues, and reminder calls that cut no-shows.
3. **Small real-estate agencies.** The pitch: every portal lead gets called within minutes and scored hot/warm/cold.
4. **Cash-on-delivery sellers** in South Asia and the Middle East, once local telephony is in place. The pitch: fewer returned parcels.

Channels:
- A demo line and the live website chat on each page for each vertical (the clinic demo is already live on the site).
- An after-hours outreach "test": call the prospect after hours, then send them the recording of our agent answering the same question.
- A reseller / agency white-label program with a 20–30% revenue share.
- Integrations as acquisition channels: Jobber, Housecall Pro, Google Calendar / Calendly, Follow Up Boss, and a Shopify app for cash-on-delivery.

**The pitch:** "Answers every call 24/7 and books it straight into your diary, for $149 a month. A receptionist costs about $3,100 a month for one shift, and an answering service charges about $5 a minute."

## 6. Next build priorities to unlock revenue

Shipped: **calendar sync** (two-way Google, iCal feed, iCal busy links) and **SMS confirmations and reminders** (Twilio Messaging, delivery receipts, per-account settings).

1. **Self-serve signup + Stripe billing** (plans, metered overage for minutes and texts). Today the admin creates accounts and sets plans.
2. **Outlook / Microsoft 365 two-way sync** (Graph API). Today Outlook uses the iCal feed and busy links.
3. **Two-way SMS**: the customer replies C to confirm or R to reschedule, and a reschedule reply triggers a call-back.
4. **Local carriers** for India / Bangladesh, and a Bangla-optimized speech-to-text option (Soniox or Sarvam benchmark far better on Bengali than OpenAI's models).
5. **HIPAA track** (business associate agreements with Twilio, OpenAI and Azure; audit log; retention controls) before selling to US clinics. SMS bodies would then need to drop the doctor's name.
