# BanglaBot — Go-to-Market (Bangladesh, Aug 2026)

**Will anyone buy at this price, and exactly how do you sell it?**

Cost basis: [COSTS.md](COSTS.md). Buyer selection: [MARKET.md](MARKET.md).
This document is the layer those two don't cover: **pricing shape, sales motion, pitch,
objections, and the first 90 days.**

Figures marked *(modelled)* are assumptions to be replaced with pilot data. Everything
else comes from the two docs above.

---

## 1. The blunt answer

**Yes — but not at the price in COSTS.md §11, and not on Twilio.**

Three findings, in order of how much they change what you do tomorrow:

### 1.1 The recommended f-commerce price is above the customer's value

COSTS.md §11 quotes ৳20–24 per plan-minute and suggests "৳25–35 per verified order."
Run that against the buyer's own arithmetic:

| Merchant: 360 orders/mo, COD, 25% RTO | |
|---|---:|
| Orders confirmed (blanket calling) | 360 |
| Connected minutes @ 1.25 min | 450 |
| **Cost to merchant** — Business plan | **৳13,000** |
| RTO prevented (25% → 8%, i.e. 17 pp) | 61 orders |
| Value per prevented RTO *(modelled, §2)* | ৳180 |
| **Value delivered** | **৳10,980** |
| **ROI** | **0.84×** |

**That is negative.** COSTS.md's own §11 benchmark says the same thing in smaller
numbers — ৳2,750 of calling to save "৳1,700–2,700" — and it was written as a selling
point. It isn't one. A Bangladeshi f-commerce seller runs 8–15% net margin and counts
every taka; they will not pay ৳13,000 to save ৳11,000. They will trial it, measure it,
and churn in month two.

MARKET.md §2 says f-commerce value/call is 8× *cost*. True. But you don't sell at cost.
At the recommended price it is **0.8× price**, and price is the only number the buyer sees.

### 1.2 The fix is a price cut you can easily afford — after Alap

At ৳1.95/min all-in, you have room the competition doesn't:

| Price to merchant | Merchant ROI | Your gross margin | Verdict |
|---:|---:|---:|---|
| ৳24/min (COSTS.md §11) | 0.7× | 92% | Unsellable |
| ৳20/min | 0.84× | 90% | Unsellable |
| ৳12/min | 1.4× | 84% | Trial, then churn |
| **৳8/min** | **2.0×** | **76%** | Sellable |
| **৳6/min** | **2.7×** | **67%** | Sells itself; matches VoiceNimble |
| ৳3/min | 5.5× | 35% | Price war, don't start here |

**But on Twilio your cost is ৳9.47/min.** Every price a merchant will actually pay is
*below your cost*. This is the whole ballgame:

> **You cannot sell f-commerce profitably until the Alap/IPTSP migration ships.**
> Selling now means either an unsellable price or a negative-margin one. Nothing in this
> document is executable before that migration. It is 1–2 weeks of work (COSTS.md §9) and
> it is worth more than any other engineering on the board.

### 1.3 Stop selling minutes. Sell answered calls.

Per-minute pricing does three bad things: it invites the ৳3/min comparison, it makes the
merchant's bill unpredictable, and it makes them mentally liable for calls nobody picks up.

Unanswered calls cost you approximately nothing (COSTS.md §2). Give that away and it
becomes the strongest line in the pitch:

> ### **৳10 per answered call. If they don't pick up, you don't pay.**
> Platform fee ৳500/month. Prepaid via bKash.

Why this specific shape wins:

- **Kills the price comparison.** ৳10/call vs ৳6/min is not an apples-to-apples the buyer
  can do in their head — and the honest translation (1.25 min × ৳6 = ৳7.5) is close enough
  that you're competitive, not expensive.
- **Removes all risk from the buyer.** The single biggest unstated objection is "what if
  nobody answers your robot?" This answers it before they ask it.
- **Matches how they think.** Merchants reason in orders, not minutes. "৳10 per order
  confirmed" maps directly onto their P&L.
- **Costs you nothing.** Your cost per connected call is ৳2.44 → **76% gross margin**.
- **Prepaid, not subscription.** Recurring card billing barely functions for BD SMBs.
  Prepaid credit top-ups over bKash — which the billing layer already does — is the norm.
  Auto-remind at 20% balance.

Run the realistic case (60% answer rate *(modelled)*, so you bill only 216 of 360 orders):

| | |
|---|---:|
| Merchant pays (216 × ৳10 + ৳500) | ৳2,660 |
| RTO prevented in the reached cohort | 32 orders |
| Value delivered | ৳5,760 |
| **Merchant ROI** | **2.2×** |
| Your cost | ৳527 |
| **Your gross margin** | **80%** |

Tier the price by voice quality using the existing multipliers: ৳8 static/keypad,
৳10 standard voices, ৳14 HD, ৳20 advance. Same catalog, different unit.

---

## 2. Rebuilding the value number honestly

MARKET.md uses ৳130 per prevented RTO — the courier fee alone. The real figure is higher,
and you should sell the full number because it is defensible line by line:

| Component | ৳ | Note |
|---|---:|---|
| Forward delivery charge, already spent | 100 | ৳60–80 Dhaka, ৳110–130 outside |
| Return charge levied by the courier | 50 | commonly ~50% of forward |
| Packaging + labelling, unrecoverable | 30 | |
| Handling, re-stocking, follow-up labour | 25 | ~10 min of someone's day |
| Damage / shrinkage on returned goods | 20 | ~5% of returns unsellable, amortised |
| Working capital locked 10–15 days | 12 | on ~৳1,200 AOV |
| **Total per prevented RTO** *(modelled)* | **~৳237** | use **৳180** in pitches — conservative sells better |

**Pitch the conservative number.** A merchant who verifies ৳180 and finds it low trusts
you. One who verifies ৳237 and finds it optimistic does not.

**What this number is not:** it excludes the ad spend burnt acquiring the order, which is
often ৳150–400 on Facebook and is the largest single loss on a failed COD order. Leave it
out of the model — but say it out loud in the meeting. It is the line that makes merchants
lean forward.

---

## 3. The targeting lever nobody in this market is pulling

Blanket-calling every order is the obvious product and the wrong one. RTO is not uniformly
distributed — it concentrates hard in a minority of customers, and the couriers already
know which ones. Fraud/reliability check APIs (delivery success ratio per phone number)
are standard in the BD courier ecosystem.

Wire that in and score every incoming order. Then:

| Strategy | Calls/mo | Merchant cost | RTO prevented | Value | ROI |
|---|---:|---:|---:|---:|---:|
| Blanket, all orders | 216 | ৳2,660 | 32 | ৳5,760 | 2.2× |
| **Risk-targeted, top 30% only** | **65** | **৳1,150** | **24** | **৳4,320** | **3.8×** |
| Hybrid — AI call on risky, static/keypad on the rest | 216 | ৳1,900 | 30 | ৳5,400 | 2.8× |

Three things this buys you:

1. **A 3.8× ROI story instead of 2.2×** — the difference between "worth trying" and "why
   isn't this already running."
2. **A defensible product.** VoiceNimble and Edesy sell minutes. "We only call the orders
   likely to fail" is a different product with a different conversation.
3. **A reason to talk to couriers** — which is your best distribution channel (§4.1).

The tradeoff is lower ARPU per merchant. Offer blanket as the default (bigger absolute
saving, bigger bill) and targeted as the answer to any price objection. Never lead with
the cheaper one.

---

## 4. How to sell it — f-commerce

**Rule: never put a human on a ৳2,660/month deal.** One founder-hour costs more than a
month of that revenue. This segment must be self-serve, community-led, or channel-led.
CAC ceiling: **৳3,000** (roughly one month of revenue, ~6-month payback with churn).

Channels, ranked by leverage:

### 4.1 Courier partnerships — the highest-leverage move available
Pathao Courier, Steadfast, RedX, eCourier, Paperfly. Between them they carry the
overwhelming majority of e-commerce parcels.

**RTO is their problem too.** A failed delivery burns a rider slot, a van kilometre, and a
warehouse touch, and they eat most of it. They have thousands of merchants already
integrated and already logging in daily.

The pitch to a courier is not "sell our product." It is: *"Let us call your merchants'
COD orders before pickup. You cut return volume on your own network, your merchants get a
higher success rate, and you take a share of the call revenue."* White-label it if they
want it branded.

One courier integration is worth more than 500 individually-acquired merchants, and it is
the only channel here that compounds without headcount. **Start here.**

### 4.2 Integrations with whatever pushes their orders to the courier
Every serious f-commerce seller uses *something* to move orders into a courier's system.
Be a one-click toggle inside that tool. Same logic as 4.1, smaller blast radius, faster
to ship.

### 4.3 Facebook seller communities — post evidence, not ads
The big seller groups are where this market actually talks. But merchants there are
saturated with claims and immune to them.

What works: **a screen recording and a table.** "Last month we ran 4,300 confirmation
calls across 12 shops. Here's the RTO before and after, per shop." Attach an actual call
recording — 40 seconds of the bot handling a real Bangla customer, including one who
interrupts. The recording does more selling than anything you can write.

Post monthly. Do not pitch in the comments; answer questions and let people DM.

### 4.4 Agency / reseller channel
The digital-marketing agencies running these pages' ad accounts already have the
relationship, the trust, and the login. Give them **20–25% recurring** and a dashboard
that shows their whole client roster. They will sell it as their own retention feature.

### 4.5 Paid ads — last
Only after you know your conversion rate and churn. At ৳2,660 ARPU the payback math is
tight and you will burn cash learning what a partnership would have taught you free.

### 4.6 The conversion mechanic — the holdout pilot
This is the single most important sales asset you will build, and it is a small feature.

> **Free: your next 200 orders. We call 100, we leave 100 alone. Then we show you the
> difference in taka.**

Automate it: random split, run for two weeks, auto-generate a one-page Bangla report —
*called cohort RTO vs. holdout cohort RTO, orders saved, taka saved, cost if you'd been
paying.* Email it and WhatsApp it.

Nothing else survives contact with a skeptical merchant. Claims don't, demos don't,
testimonials don't. **Their own numbers do.** Build the auto-report before you build
anything else on the growth side — it is the difference between a 10% and a 40% trial
conversion rate.

---

## 5. How to sell it — Tier A enterprise

Different motion entirely: founder-led, long, and worth roughly a thousand times more.

**One mid-sized MFI is worth your entire f-commerce book.** 200,000 borrowers, weekly
cadence, called at ৳15/borrower/month = **৳3,000,000/month from one contract.** Even a
50,000-borrower institution is ৳750,000/month — more than 280 f-commerce merchants, from
one relationship. That comparison is why f-commerce is a data source and a proof point,
not the destination (MARKET.md §7).

### 5.1 Sequence
MFI → life insurance → banks. Ascending procurement friction, descending speed to first
taka. Do not start with a bank because the logo is impressive; you will spend nine months
in a security review with no revenue and no reference.

### 5.2 Who you actually contact
Not the MD. The person whose bonus depends on the metric:

| Vertical | Title | The metric they're measured on |
|---|---|---|
| MFI | Head of Microfinance Programme / Head of Operations | on-time collection rate |
| MFI | Regional / Zonal Manager | branch-level recovery, field officer productivity |
| Life insurance | Head of Renewals / Persistency, or the CFO | persistency ratio, lapse rate |
| Bank / NBFI | Head of the (now mandatory) Recovery Unit | 1–30 DPD roll rates, provisioning |

### 5.3 The opening asset — send audio, not a deck
Before the first meeting, build a 60-second Bangla call demo **of their exact use case**,
using their institution's name, their product's terms, their borrower's situation. Send it
as an audio file with three lines of text.

In this market an audio file of the bot doing their job books meetings that no slide deck
books. It also pre-empts the entire "will this work in Bangla" conversation, which is
otherwise the first 20 minutes of every meeting.

### 5.4 The offer for the first three customers
> **Free 90-day pilot. One branch, one control branch, one metric.
> In exchange: the right to publish the result, anonymised.**

You need referenceable numbers far more than you need the pilot fee. MFIs already run
branch-level reporting, which means they can approve a single-branch pilot **without going
through procurement** — that is why they're first in the sequence.

Instrument exactly one metric: on-time collection rate, test branch vs. control. Resist
every temptation to measure five things.

### 5.5 Pricing enterprise
Never per minute (MARKET.md §9.2). Structure as **floor + outcome**:

| Vertical | Shape |
|---|---|
| MFI | ৳12–18 per active borrower per month, floor ৳2 lakh/mo |
| Insurance | ৳500/policy contacted **+ 3–5% of first-year premium saved** on renewals attributable to a call |
| Bank collections | 1.5–3% of amount recovered in the 1–30 DPD bucket, with a monthly floor |

The floor covers your infrastructure and keeps you honest about deployment cost. The
outcome component is what makes the number un-negotiable — they're paying out of money
they otherwise wouldn't have had.

**Prerequisite:** outcome pricing is only measurable if the call closes the loop. Ship
bKash/Nagad payment links in-call (MARKET.md §9.3) before you quote a percentage of
anything.

---

## 6. Objection handling

These are the six you will hear. Have the answer ready verbatim.

**"Customers won't talk to a robot — they'll hang up."**
The only real objection. Answer with data, not reassurance: your own connect rate,
completion rate, and average call duration from live logs. Then de-risk it structurally —
`transfer_to_human` on any confusion, and the static/keypad tier as a fallback for
merchants who won't accept a conversational bot at all. Close with: *"And you only pay for
calls that get answered."*
→ *Product implication:* surface connect rate and completion rate on the merchant
dashboard. It is your best sales collateral and it updates itself.

**"I already have staff who call."**
Don't argue that you're cheaper per minute — you aren't (COSTS.md §11: ৳5–7/min for a
caller). Argue on the four things a person cannot do: call 100 orders in ten minutes; call
at 9 PM and on Friday when customers actually pick up; call the 300-order day the same way
as the 30-order day; and produce a recording and transcript of every one. Then: *"Keep the
staff. Let them handle the 20 calls that need a human, and give us the 180 that don't."*

**"VoiceNimble is ৳6/min. Edesy is $0.04."**
Don't fight on price — you'll win and it teaches the market the wrong lesson. Fight on
three things they can hear in ten seconds: **bn-BD accent** (Edesy and the global platforms
serve Indian Bengali or untuned Bengali — play both, the difference is obvious), **a local
+880 caller ID** that gets answered far more often than a foreign number, and **the loop
closing** — your call cancels the order in their system and stops the parcel; a competitor's
call just logs an intent. Hold the price. If a deal genuinely turns on it, move to
risk-targeted calling (§3) so the *bill* drops without the *rate* dropping.

**"Is this legal? Will BTRC give me trouble?"**
Turn it into a feature. Registered caller ID, calling-window enforcement in the scheduler,
consent language in the opening line, recordings retained and exportable. *"We built the
compliance in so you don't have to think about it."* Have this ready before the first
enterprise meeting; in regulated verticals it is the reason you win (MARKET.md §3, §10.3).

**"Prove it works for my shop."**
The holdout pilot (§4.6). Never argue past this objection — accept it immediately and run
the test. The merchants who ask this are your best customers.

**Enterprise: "Our data cannot leave our network."**
Have the VPC / on-prem answer written down before the meeting, not invented in it. It's
also a moat: every competitor selling a hosted-only Shopify app is disqualified from the
entire regulated market (MARKET.md §9.4).

---

## 7. What must ship before you sell

In order. Each one blocks the next.

| # | Item | Blocks | Est. |
|---|---|---|---|
| 1 | **Alap / IPTSP migration** | any profitable f-commerce price at all | 1–2 wk |
| 2 | **Reprice to ৳/answered call, prepaid via bKash** | conversion; kills the ৳/min comparison | 2–3 d |
| 3 | **Holdout pilot + auto-generated RTO delta report** | trial→paid conversion | ~1 wk |
| 4 | **Courier fraud-check integration + risk score** | the 3.8× ROI story and the courier conversation | ~1 wk |
| 5 | **Connect / completion rate on the merchant dashboard** | the "nobody talks to robots" objection | 2 d |
| 6 | **Campaign-type refactor** (MARKET.md §9.1) | every Tier A vertical | ~2 wk |
| 7 | **bKash payment link in-call** | outcome-based enterprise pricing | ~1 wk |

Items 1–5 are roughly a month and unlock the self-serve business. 6–7 are another three
weeks and unlock the one worth a hundred times more.

---

## 8. The next 90 days

**Days 1–30 — make it sellable**
Ship items 1–3. Run the holdout pilot on your existing merchants and on five new ones
recruited free from seller groups. Target: **20 completed pilots with measured deltas.**
No pricing conversations, no ads, no partnership meetings. You are buying evidence.

**Days 31–60 — prove the channel**
Publish the aggregate pilot result. Convert the pilots at the new ৳/answered-call price.
Approach **three couriers** with the aggregate data — that meeting only works once you can
say "here is the measured RTO reduction across 20 shops." Ship items 4–5.
Target: **25 paying merchants, one courier in active discussion.**

**Days 61–90 — open the second front**
Ship item 6. Build the installment-reminder campaign type and the 60-second MFI audio
demo. Approach **five MFIs** for a single-branch free pilot. In parallel, three life
insurers with the sector's own published lapse commentary as the opening slide
(MARKET.md §4.2).
Target: **one MFI branch pilot live, 50 paying merchants.**

---

## 9. Targets, and when to stop

| Horizon | F-commerce | Enterprise | MRR |
|---|---:|---:|---:|
| 90 days | 50 merchants | 1 MFI pilot (unpaid) | ~৳130,000 |
| 6 months | 150 merchants + 1 courier channel | 1 MFI paid, 1 insurer pilot | ~৳600,000 |
| 12 months | 400 merchants | 2 MFI, 1 insurer | ~৳3,000,000 |

Break-even against the ৳4,600/mo fixed base (COSTS.md §8) is **three merchants.** Cash is
not the constraint here; evidence and distribution are.

**Kill criteria — decide these now, while you're unattached to the answer:**

- **Measured RTO delta across 20 pilots is under 8 pp** → the f-commerce ROI story does not
  hold at any price. Keep the product running self-serve at whatever it clears, stop all
  growth spend on it, and move entirely to Tier A.
- **Connect rate below 45%** → the problem is caller ID, calling windows, or the opening
  three seconds — not the product. Fix it before spending another taka on acquisition.
- **No courier conversation reaches pilot within 6 months** → f-commerce has no scalable
  channel for you. Cap it, harvest it for training data and reference logos exactly as
  MARKET.md §7 says, and put 100% of your time on MFIs.

---

## 10. If you remember four things

1. **Ship Alap before you sell anything.** On Twilio, every price a merchant will pay is
   below your cost. Nothing else on this page is executable until that's done.
2. **৳10 per answered call, unanswered free, prepaid on bKash.** Not ৳20/minute. The
   current recommended price is above the value you deliver, and merchants will do that
   arithmetic in month two whether or not you do it in month one.
3. **The holdout pilot is your product's real sales team.** Their numbers, not your claims.
   Build the auto-report; it is a week of work and it is the difference between a business
   and a demo.
4. **F-commerce is the proof, not the plan.** One mid-sized MFI contract outweighs your
   entire merchant book. Spend f-commerce effort on things that compound — the courier
   channel, the call recordings, the reference logos — and spend your own hours on Tier A.

---

## 11. On the numbers in this document

Costs are from [COSTS.md](COSTS.md) and are measured. Market sizes, competitor pricing and
sector data are sourced in [MARKET.md](MARKET.md) §13.

**Modelled here and requiring pilot validation:** value per prevented RTO (§2), the 60%
answer rate, RTO reduction of 17 pp blanket / 25 pp on the risk-targeted cohort, the
risk-cohort concentration in §3, and every enterprise ARPU figure in §5. These establish
orders of magnitude and decide direction — they are not forecasts. Replace each with real
numbers as the first twenty pilots land, and revisit §1.2 in particular: **the price
recommendation moves if the measured RTO delta moves.**
