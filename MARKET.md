# BanglaBot — Market Analysis (Bangladesh, Aug 2026)

**Where a Bangla voice agent actually sells, and who will buy it without arguing about price.**

Cost basis: this repo's [COSTS.md](COSTS.md), at ৳123/USD.
Market figures are sourced (§10). Value-per-call figures are **modelled estimates** — see §9.

---

## 1. The thesis

**Your cost is already solved. Your buyer isn't.**

At ৳1.95/min on local telephony, a 1.25-minute confirmation call costs **৳2.44**. That is not
expensive in absolute terms — it is expensive *relative to what an f-commerce seller's call is
worth*. One prevented RTO saves a merchant ~৳130 in courier cost, times maybe a 15-point RTO
reduction: roughly **৳20 of value per call**. Eight times your cost.

That thin 8× ratio is why the market bargains, why competitors have already pushed the price to
৳3–6/min, and why the whole category feels like it can't afford you.

Cutting cost from ৳1.95 to ৳1.35 does not fix an 8× ratio. **Changing the buyer does.** Point the
identical pipeline at a microfinance installment, a lapsing life policy, or an admission lead and
the value per call moves by two orders of magnitude while your cost stays at ৳2.44.

---

## 2. The value-per-call ladder

The right question is not "who has money." It is **what is one successful call worth to the person
paying for it?**

Value below = amount at stake in the underlying transaction × a conservative lift the call can
plausibly produce. Sorted by value, not by recommendation.

| Tier | Vertical | Value at stake | Assumed lift | **Value / call** | vs ৳2.44 cost |
|---|---|---:|---:|---:|---:|
| C | Overseas recruitment placement | ৳4,00,000 | 0.3 pp | **৳1,200** | 500× |
| B | Real-estate apartment lead | ৳2,50,000 | 0.4 pp | **৳1,000** | 417× |
| B | Private-university admission lead | ৳1,20,000 | 0.8 pp | **৳960** | 400× |
| **A** | Bank / NBFI card at 30 DPD | ৳45,000 | 2 pp | **৳900** | 375× |
| **A** | Life-insurance renewal (lapse save) | ৳18,000 | 4 pp | **৳720** | 300× |
| B | Diagnostic appointment / no-show | ৳3,500 | 12 pp | **৳420** | 175× |
| **A** | MFI weekly installment reminder | ৳800 | 5 pp + saved field visit | **৳60** | 25× |
| D | F-commerce COD confirmation | ৳130 | 15 pp | **৳20** | 8× |

**Read the tiers against the positions.** The three Tier A verticals are *not* the three highest
values. Value per call is only one of four filters — and the top of the ladder (recruitment, real
estate) fails the others. **Highest value per call ≠ best market.**

---

## 3. The four filters

| Filter | What it asks | What kills a vertical |
|---|---|---|
| **Value per call** | Is one good call worth 100× what it costs to place? | Under ~30× the buyer negotiates on ৳/minute forever. |
| **Buyer concentration** | How many contracts to reach meaningful revenue? | 300,000 tiny buyers means sales cost exceeds ARPU. |
| **Voice necessity** | Would SMS or WhatsApp do the job just as well? | If the end user reads fluently and has a smartphone, voice is a luxury. |
| **Regulatory posture** | Does compliance help you or block you? | Neutral is fine; hostile (unlicensed telemarketing) is fatal. |

The fourth filter is the one most people miss, and in Bangladesh it is **positive** for exactly the
verticals at the top of the ranking.

Bangladesh Bank now requires every bank to run a recovery unit supervised by the Managing Director,
and requires recovery agents to avoid harassment and coercion. Human recovery calling in Bangladesh
has a reputation problem. A script-bounded agent that never raises its voice and produces a full
recording and transcript of every call is not just cheaper than a collections team — it is **a
compliance artifact the bank cannot buy any other way.** That is what turns "how much per minute?"
into "how fast can you deploy?"

---

## 4. Tier A — build for these now

*High value per call, few buyers, voice genuinely required, regulation helps.*

### A1. Microfinance installment reminders & pre-meeting calls
**Highest volume in the country.**

731 MRA-licensed MFIs serve **40.86 million members and 31.53 million borrowers** through 25,336
branches and 200,000+ staff. ~90% of clients are women, largely rural, on a **weekly** repayment
cadence.

The comparison is not a call-centre agent at ৳5–7/min — it is **a field officer's time and travel**,
which is far more expensive per contact.

This is the only vertical in Bangladesh where voice is not a preference but a requirement: the
borrower base skews low-literacy, so SMS and WhatsApp genuinely do not land. A Bangla voice call the
day before a group meeting is the cheapest possible intervention on the single metric every MFI
reports — **on-time collection rate**.

Buyer concentration is excellent: the ten largest microcredit institutions plus Grameen Bank hold
**81% of outstanding loans**. Eleven conversations reach most of the market.

| | |
|---|---|
| Addressable contacts | 31.5M borrowers |
| Natural cadence | Weekly |
| Buyers for ~80% coverage | ~11 |
| Value / call | ৳60 (25×) |
| Sales cycle | 2–4 months |

### A2. Life-insurance renewal and lapse prevention
**The clearest documented pain.**

The sector's own press describes this precisely: new policy sales are rising while **retaining
existing customers is the industry's biggest challenge**. The named causes read almost like a
product spec — agents lose contact with clients after the first-year commission, after-sales service
is weak, and digital renewal systems are limited.

The economics are brutal in your favour. A lapsed policy forfeits an already-paid acquisition cost
*and* the entire remaining premium stream. On a ৳18,000 annual premium with several years left to
run, a single saved policy pays for tens of thousands of calls. No insurer will negotiate ৳/minute
against that.

Policyholder benefit is unusually strong here, which matters for how this gets received: on lapse
the customer forfeits years of their own money. A call preventing that is a service, not a nuisance —
and it fills the exact gap the vanished agent left.

| | |
|---|---|
| Buyers in market | ~35 life insurers |
| Natural cadence | Quarterly / annual |
| Value / call | ৳720 (300×) |
| End-user benefit | Very high |
| Sales cycle | 3–6 months |

### A3. Bank & NBFI early-bucket collections
**Biggest budget, hardest procurement.**

NPLs reached roughly **৳5.89 lakh crore — 32.26% of total bank credit** as of March 2026, up from
24.13% a year earlier. Bangladesh Bank has responded with mandatory MD-supervised recovery units,
ADR recovery targets, and explicit conduct rules for recovery agents.

**Do not chase the deep NPL book** — that is lawyers and courts. Chase **1–30 days past due**, where
a polite reminder actually changes behaviour and where human agents are most wasted. Pair it with a
bKash/Nagad payment link sent during the call so the conversation closes the loop instead of merely
logging an intent.

Expect the longest sales cycle of any Tier A vertical, a security review, and a likely requirement
to deploy inside the bank's own VPC rather than on the current Supabase-hosted stack. Price it
accordingly — this is where per-outcome or percentage-of-recovery pricing belongs.

| | |
|---|---|
| Buyers in market | ~61 banks + ~35 NBFIs |
| Value / call | ৳900 (375×) |
| Sales cycle | 6–12 months |
| Blocker | On-prem / VPC deployment |

---

## 5. Tier B — the fast follow

*Excellent unit value, but seasonal, lumpy, or smaller in volume.*

### Private universities & coaching centres — admission lead calling
115 private universities compete for the same applicant pool in tight seasonal windows. Lifetime
tuition of ৳4–8 lakh means a single incremental enrolment justifies an enormous calling budget. The
catch is seasonality — this is a campaign business, not a subscription, so **price per qualified
lead**, not per minute. Coaching centres and the fee-reminder use case extend it across the rest of
the year.

### Diagnostic chains & hospitals
Labaid alone reports **~3 million annual patient encounters**. Four distinct call types stack on one
contract:

1. Appointment confirmation
2. **Test-preparation instructions** (fasting, timing) — a real clinical benefit, and impossible over
   SMS for many patients
3. Report-ready notification — enormous volume on its own
4. Follow-up recall

Patient benefit is genuine and defensible, which makes this the best vertical for public credibility.

### Real-estate developers — instant lead callback
Willingness to pay is near-unlimited per lead and the incumbent behaviour already exists: Sheltech
openly recruits for a "Call Center & Data Management" function handling Facebook, WhatsApp,
Instagram and website enquiries. The winning pitch is **speed** — calling a Facebook lead within 30
seconds, at 11pm, in Bangla. Volume per customer is low, so this is high-ARPU / low-count, not a
scale play.

---

## 6. Tier C — opportunistic

### Donor-funded phone surveys (CATI replacement)
Development-sector telephone surveys in Bangladesh run at CATI rates funded by grant budgets, and
the published research is explicit that **keypad IVR underperforms human CATI on completion,
response and cooperation rates**. An LLM voice agent sits precisely in that gap: CATI-quality
conversation at IVR economics. Donors are the least price-sensitive buyers in the country.

Downside: project work, not SaaS. Good cash, poor multiples, slow procurement.

### Overseas recruitment agencies
Bangladesh deployed **750,000+ workers to Saudi Arabia in 2025** alone, through ~2,646 licensed
agencies. Value per placement is the highest on the ladder, and the migrant worker benefit is real —
this population is chronically defrauded by sub-agents, and a recorded, verifiable Bangla
status-update channel is genuine protection.

But the sector's reputation is poor and a fraction of your customers would be bad actors. Enter only
with strict recording, consent, and customer-vetting policy in place.

---

## 7. Tier D — keep it, but stop calling it the business

### F-commerce COD confirmation
The market is real — roughly **300,000 Facebook-page sellers** against ~$1 billion in annual
f-commerce revenue, with COD RTO commonly cited at 20–30%.

But value per call is ~8× your cost, ARPU is low, churn is high, and the space is already contested:

| Competitor | Pricing | Position |
|---|---|---|
| VoiceNimble | ৳3/min IVR, **৳6/min AI conversation** + ৳500/mo platform fee; setup ৳5k–50k | Direct competitor, BD-focused, Shopify app |
| AIM24 (Dhaka, ICT Tower) | n/a | Piloting with Dhaka e-commerce shops, on Play Store |
| Edesy (India) | from **$0.04/min** (≈৳4.92) | Advertises BD coverage; still 2× your all-in cost |
| OpenMic.ai | global | Lists Bengali, doesn't tune it |

**Keep it.** It is your working proof, your reference logos, and your source of real Bangla call
recordings to tune on. Just stop treating a market that caps out at ৳20 of value per call as the
destination, and stop spending engineering time defending it on price.

---

## 8. The two lists you asked for

### Who won't think about the money
*Ranked by how badly one successful call outweighs its price.*

1. **Recruitment agency placing a worker** — ৳3–5 lakh fee per placement
2. **Developer closing an apartment** — margin on a ৳50 lakh–2 crore unit
3. **University enrolling one student** — ৳4–8 lakh of tuition
4. **Bank curing a 30-DPD card balance** — plus provisioning relief and a compliance record
5. **Insurer saving a lapsing policy** — sunk acquisition cost plus the whole remaining premium stream

### Where the end user genuinely gains
*Ranked by real benefit to the person receiving the call.*

1. **Rural MFI borrower** — literacy makes voice the only working channel; avoids penalty and the
   pressure of a field visit
2. **Policyholder near lapse** — prevents forfeiting years of their own premiums
3. **Patient before a test** — fasting and preparation instructions they can actually follow
4. **Migrant worker in process** — verified, recorded status updates in a sector built on rumour
5. **COD buyer** — mild: fewer wrong deliveries

> The two lists overlap on **microfinance and insurance**. That overlap is the answer to the
> question actually being asked: the vertical where the buyer stops caring about price *and* the
> recipient is better off is the one where the product compounds instead of grinding.

---

## 9. What has to change in the product

### 9.1 Generalise the record, not the pipeline
Roughly 80% of what's built is already vertical-agnostic — multi-tenant merchants, voice tiers,
entitlements and billing, call logs, recordings, audit trail, `transfer_to_human`.

What is hard-coded to e-commerce is narrow:

- `backend/app/models/order.py` — the `Order` model
- `backend/app/voice/prompts.py` — the Bengali system prompt
- `backend/app/voice/tools.py` — `confirm_order` / `cancel_order`

Replace that with a **campaign type**: a target record schema, a prompt template, an outcome tool
set, and a schedule. Order confirmation becomes one campaign type among:

| Campaign type | Target record | Outcome tools |
|---|---|---|
| Order Confirmation | Order | confirm / cancel / reschedule |
| Installment Reminder | Loan + due installment | acknowledged / promise-to-pay / dispute |
| Policy Renewal | Policy + premium due | will-renew / payment-link-sent / lapse-intent |
| Appointment Confirmation | Appointment + prep instructions | confirm / reschedule / cancel |
| Lead Qualification | Lead | qualified / not-interested / callback |

That single refactor is what lets one codebase address every vertical above. Estimated ~2 weeks.

### 9.2 Stop selling minutes
Per-minute pricing is a race you lose — it invites the ৳3/min comparison and caps you at the cost of
the cheapest competitor. Price on the outcome the buyer already measures:

| Vertical | Sell the unit they already report | Not this |
|---|---|---|
| Microfinance | ৳ per borrower per month, tied to on-time collection rate | ৳/min |
| Insurance | ৳ per policy saved, or a share of recovered premium | ৳/min |
| Bank collections | % of amount recovered in the 1–30 DPD bucket | ৳/min |
| University | ৳ per qualified lead delivered | ৳/min |
| Diagnostics | ৳ per confirmed appointment | ৳/min |

### 9.3 Close the loop with bKash / Nagad
A collection or renewal call that ends in an *intent* is worth a fraction of one that ends in a
*payment*. Sending a bKash payment link during the call — "আমি বিকাশ লিংক পাঠিয়ে দিচ্ছি" — converts
a soft metric into a hard, attributable one. It is also the single feature that makes outcome-based
pricing measurable, which is what unlocks §9.2.

### 9.4 Two things regulated buyers will demand
- **Full call recording + Bangla transcript, retained and exportable.** `recording_service.py` and
  audit logging already exist — this is packaging, not building.
- **A deployment story that isn't managed cloud.** Banks and larger insurers will require the stack
  inside their own environment. Solve it once and it becomes a barrier to every competitor selling a
  hosted-only Shopify app.

---

## 10. Your actual moat

Three things, and none of them is the AI:

1. **The ৳0.40/min local trunk.** Foreign vendors advertising Bangladesh at $0.04/min are quoting
   ৳4.92 — more than double your entire all-in cost. Alap/IPTSP economics are not available to
   anyone routing through Twilio, and a local +880 caller ID gets answered far more often than a
   foreign number.
2. **Bangla quality as a product, not a checkbox.** Global platforms list Bengali; they don't tune
   it. The four named speaker tiers and dialect handling are the difference between a call that
   completes and one that gets hung up on.
3. **Compliance packaging.** Recording, transcript, audit trail, conduct-bounded scripts. Irrelevant
   in f-commerce; decisive in every regulated vertical above.

---

## 11. Risks worth naming

| Risk | Why it matters | Mitigation |
|---|---|---|
| **BTRC telemarketing rules** | Automated outbound from a +880 business number falls under caller-ID registration and calling-hour limits | Register early; build calling-window enforcement into the scheduler before you need it |
| **Recovery-agent conduct rules** | Bangladesh Bank explicitly prohibits harassment and coercion in loan recovery | Cuts both ways — make it the selling point. Publish the guardrails |
| **Borrower / patient data residency** | MFI and hospital data on a foreign-hosted DB is a procurement blocker, not a preference | Have a VPC / on-prem answer ready before the first bank meeting |
| **Sales cost per contract** | Tier A means enterprise selling — a very different motion from signing Facebook sellers | Start with MFIs: fastest procurement of the three, largest volume, least security friction |

---

## 12. The next 90 days

1. **Finish the Alap/IPTSP migration.** Nothing else matters until the ৳7.52/min Twilio premium is
   gone — it is larger than the entire AI stack, and it is the moat. (COSTS.md §9, §12)
2. **Refactor `Order` into a campaign-type abstraction.** ~2 weeks; converts a single-vertical
   product into a platform.
3. **Build the installment-reminder campaign type** and pilot with one mid-sized MFI. Instrument one
   metric only: on-time collection rate versus a control branch.
4. **Build the renewal campaign type** and take the lapse-prevention pitch to three life insurers,
   with the sector's own published complaints as the opening slide.
5. **Ship bKash payment links in-call** — this is what makes outcome pricing possible.
6. **Keep f-commerce running unchanged.** Reference logos and Bangla training data.

---

## 13. On the numbers in this document

Cost figures come from [COSTS.md](COSTS.md) and are measured. Market sizes, borrower counts, NPL
ratios, lapse commentary and competitor pricing are sourced below. **The value-per-call figures in
§2 are modelled estimates** — transaction value × a conservative lift assumption — meant to
establish orders of magnitude, not forecast revenue. Replace each with pilot data as it arrives.

### Sources

- **Microfinance sector** — [Bangladesh Bank](https://www.bb.org.bd/saarcfinance/seminar/cpbdesh.php),
  [MRA sector snapshot](https://www.linkedin.com/pulse/snapshot-bangladeshs-microfinance-sector-2022-s-m-moinur-rahman-moin-1c):
  731 MFIs, 40.86M members, 31.53M borrowers, 25,336 branches, ~200k staff, ~90% women clients,
  top 10 + Grameen = 81% of outstanding loans.
- **Life insurance lapses** — [The Business Standard](https://www.tbsnews.net/economy/stocks/rising-policy-lapses-reflect-growing-public-distrust-life-insurers-1302186):
  retention as the sector's biggest challenge; agents losing contact after first-year commission;
  limited digital renewal systems.
- **NPL crisis** — [Dhaka Tribune](https://www.dhakatribune.com/business/banks/414263/npl-crisis-can-bangladesh-bank-recover-tk5.88),
  [The Daily Star](https://www.thedailystar.net/business/news/strategic-exit-policy-resolving-non-performing-loans-4227511):
  ৳5.89 lakh crore NPL, 32.26% of credit (Mar 2026), MD-supervised recovery units, ADR targets.
- **Recovery conduct rules** — [Jural Acuity](https://juralacuity.com/loan-recovery-laws-in-bangladesh/).
- **COD RTO rates & couriers** — [Bangladesh e-commerce market entry](https://easysellapp.com/blogs/wiki/bangladesh-ecommerce-bkash-mobile-money-cod-shopify-market-entry-2026):
  20–30% RTO on COD; Pathao/RedX/Steadfast = 95% of e-commerce delivery.
- **F-commerce size** — [Bangladesh digital statistics 2026](https://agentwisex.com/bangladesh-digital-marketing-statistics-2026/),
  [Dhaka Tribune](https://www.dhakatribune.com/business/281034/f-commerce-is-the-new-shopping-mall):
  ~300,000 Facebook-page sellers, ~$1B annual f-commerce revenue.
- **Competitors** — [VoiceNimble](https://voicenimble.com/) (৳3/min IVR, ৳6/min AI conversation,
  ৳500/mo platform fee), [Edesy](https://edesy.in/ai-voice-agent/markets/bangladesh) (from $0.04/min),
  [AIM24](https://www.nucamp.co/blog/coding-bootcamp-bangladesh-bgd-bangladeshs-top-10-startups-that-tech-professionals-should-watch-out-for-in-2025).
- **Hospital volume** — [Labaid profile](https://rocketreach.co/labaid-hospitals-and-diagnostics-profile_b5bf13b0f66348fe):
  ~3M annual patient encounters, ~8,000 employees.
- **Real estate call centres** — [Sheltech job listing](https://bdjobs.com/h/details/1515977?ln=1):
  inbound/outbound, Facebook/WhatsApp/Instagram lead handling, telemarketing.
- **IVR vs CATI** — [Mobile phone survey participation in Bangladesh](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10160933),
  [IVR vs CATI comparison](https://clinicaltrials.gov/study/NCT04508010): IVR underperforms CATI on
  completion, response and cooperation rates.
- **Overseas recruitment** — [Bangladeshi workers in Saudi Arabia 2026](https://manpower.com.bd/insights/global-mobility/bangladeshi-workers-saudi-arabia-2026),
  [TBS on recruiting agencies](https://www.tbsnews.net/bangladesh/shrinking-labour-market-growing-recruiting-agencies-despite-white-papers-red-flag):
  750,000+ deployed to Saudi Arabia in 2025; 2,646 licensed agencies.
- **Private universities** — [UniHub admission guide 2026](https://unihub.bd/blogs/complete-guide-to-bangladesh-university-admission-2026-everything-you-need-to-know):
  115 private universities.
- **RMG worker helpline** — [Amader Kotha](https://amaderkothahelpline.net/about-us/): brand-funded
  grievance line, ~3,000 calls/month, 233,000+ calls to date.
