# Cost, pricing and profit review

*2026-10-16. Based on the three real test calls made on the live system on 2026-10-15
(the demo clinic and the demo home-service accounts) and the platform's own price list
(`backend/app/finance/pricebook_defaults.py`). Prices are list prices; re-check before relying on them.*

## 1. Which speech services a call uses

| Part | Live server (Render) | Your laptop |
|---|---|---|
| Speech-to-text | **Deepgram Nova-3** | Local Parakeet (GPU), then Deepgram |
| Text-to-speech | **Deepgram Aura-2**, voice `aura-2-thalia-en`; if it fails: Gemini → Edge → Azure | Local Kokoro (GPU), then Deepgram |
| LLM | Groq gpt-oss-120b (free tier) today; **OpenAI gpt-5.4-mini** in production | same |

The finance ledger confirms every test call used Deepgram for both directions.

## 2. What the test calls actually cost

| Call | Length | Caller | Agent | Phone line | Speech-to-text | Voice | LLM* | **Total** | **Per minute** |
|---|---|---|---|---|---|---|---|---|---|
| Home service | 2 m 22 s | 9 turns, 65 words | 18 turns, 175 words (970 chars) | $0.0270 | $0.0079 | $0.0154 | $0.0041 | **$0.054** | **$0.023** |
| Clinic | 1 m 59 s | 7 turns, 49 words | 14 turns, 142 words (787 chars) | $0.0180 | $0.0053 | $0.0161 | $0.0024 | **$0.042** | **$0.021** |
| Clinic | 48 s | 3 turns, 36 words | 5 turns, 66 words (375 chars) | $0.0090 | $0.0027 | $0.0034 | $0.0013 | **$0.016** | **$0.021** |
| **All three** | **5.15 min** | | | 48 % | 14 % | 31 % | 7 % | **$0.113** | **$0.022** |

\* The LLM was free (Groq) during the test. The column shows what OpenAI gpt-5.4-mini would
have cost for the same tokens.

What the numbers show:
- **The agent talks about 400 characters a minute; callers say about 25–45 words a minute.**
- **The audio cache already saved $0.029 (about 20 %).** 32–70 % of everything the agent said came
  from the cache instead of being paid for again. That share grows as fixed lines get reused.
- **Speech-to-text is billed only while the caller talks** (1.02 of 2.37 minutes on the home-service
  call), because caller audio isn't streamed while the agent speaks.
- **Telnyx charges per started minute** (a 48 s call is billed as 1 minute). This is included
  above; it adds about 16 % to the phone line.
- **Production cost to plan with: ≈ $0.022 per minute, or ≈ $0.025 including texts** (≈ 1.5 texts
  per booking). The earlier estimate in `pricing.md` was ≈ $0.05, so margins are better than planned.

## 2a. The real all-in cost per minute

The $0.022 above covers only what a call itself costs (phone minutes, speech-to-text, voice, LLM).
The all-in number also spreads every other bill over the minutes customers use:
- phone numbers: $1/month each;
- texts;
- hosting (Render), database (Supabase), website (Vercel), Redis, domain;
- SMS registration (10DLC);
- monitoring;
- card fees (2.9 % + 30¢).

Assumed customer mix: 50 % Starter / 35 % Growth / 15 % Pro, each using 60 % of the included minutes
and texts. That's about 333 minutes and $129 revenue per customer per month.

| Per minute | Launch (5 customers) | Early (20) | Growing (100) | 100 simultaneous calls (≈ 470) |
|---|---|---|---|---|
| Minutes used per month | 1,665 | 6,660 | 33,300 | 156,500 |
| Call itself (phone minutes, speech-to-text, voice, LLM) | $0.0219 | $0.0219 | $0.0219 | $0.0219 |
| Phone numbers | $0.0050 | $0.0050 | $0.0050 | $0.0050 |
| Texts | $0.0052 | $0.0052 | $0.0052 | $0.0052 |
| Hosting + database + website + domain + SMS registration | $0.0486 ($81/mo) | $0.0122 ($81/mo) | $0.0046 ($152/mo) | $0.0020 ($317/mo) |
| Card fees | $0.0121 | $0.0121 | $0.0121 | $0.0121 |
| **All-in cost per minute** | **$0.093** | **$0.056** | **$0.049** | **$0.046** |
| Revenue per minute used | $0.387 | $0.387 | $0.387 | $0.387 |
| **Profit per minute** | **$0.295** | **$0.331** | **$0.339** | **$0.341** |
| Monthly cost → revenue → **profit** | $155 → $645 → **$490** (76 %) | $375 → $2,580 → **$2,205** (85 %) | $1,624 → $12,900 → **$11,276** (87 %) | $7,234 → $60,630 → **$53,396** (88 %) |

Fixed costs dominate only at the very start. With a single Starter customer, the $81 fixed bill
makes that month a $39 loss. **Break-even is about 2 customers.** From about 20 customers, the
all-in cost settles near $0.05 per minute against $0.39 of revenue.

Still not included: your own time, support staff, marketing, refunds/chargebacks, taxes,
company and accounting fees.

## 3. Are the plans and prices OK?

Yes. Every plan keeps 80–89 % gross margin even if the customer uses every included minute.

| Plan | Price | Included | Our cost at 100 % use | **Profit** | Margin | At typical 60 % use | Overage margin |
|---|---|---|---|---|---|---|---|
| Chat agent | $29 | 1,000 chats | $5.14 | **$23.86** | 82 % | — | — |
| Starter | $49 | 150 min, 1 number, 100 texts | $7.02 | **$41.98** | 86 % | $43.70 (89 %) | $0.30/min → 92 % |
| Growth | $149 | 600 min, 2 numbers, 500 texts | $24.37 | **$124.63** | 84 % | $131.73 (88 %) | $0.22/min → 89 % |
| Pro | $349 | 1,800 min, 3 numbers, 2,000 texts | $69.42 | **$279.58** | 80 % | $301.98 (87 %) | $0.16/min → 84 % |
| Enterprise | from $999 | custom | — | — | — | — | $0.10/min → 75 % |
| Extra 100 minutes | $25 | 100 min | $2.50 | **$22.50** | 90 % | — | — |
| Free trial (14 days) | $0 | 50 min, 50 texts | ≈ $2 per signup | — | — | — | — |

Costs include usage, $1/month per phone number, texts at $0.0055, and card fees (2.9 % + 30¢).

**Suggestions:**
1. **Starter: consider 200 minutes instead of 150.** Rosie gives 250 minutes for $49 and Trillet 150.
   The extra 50 minutes cost us $1.25, and the margin stays about 84 %.
2. **Keep the other prices.** They sit in the middle of the small-business market ($29–349;
   see `pricing.md` §2) with plenty of room for discounts or a cheaper LLM later.
3. **Minutes are billed to customers per second** while we pay per started minute. That's
   customer-friendly, and the margins above already include it. Rounding customers up to the
   minute (as most competitors do) would add about 10–15 % margin on short calls.

**Expected monthly profit** (customer mix 50 % Starter / 35 % Growth / 15 % Pro, each using 60 %
of their minutes, including servers):

| Customers | Revenue | All costs | **Profit** | Margin |
|---|---|---|---|---|
| 20 | $2,580 | $400 | **$2,180** | 84 % |
| 100 | $12,900 | $1,725 | **$11,175** | 87 % |
| 500 | $64,500 | $8,274 | **$56,226** | 87 % |

Not included: your own time, support, marketing, refunds, taxes.

## 4. Fully paid production sized for 100 simultaneous calls

**Fixed monthly infrastructure: ≈ $200–400/month**

| Item | Size | Monthly |
|---|---|---|
| App servers (Render) | 5 × Standard (1 CPU / 2 GB, ~30 live calls each, one spare) or 3 × Pro (2 CPU / 4 GB) | $125–255 |
| Redis (shared call counters, rate limits, live-call view) | Render Key Value | $10–32 |
| Database + audio cache (Supabase Pro + small compute add-on) | | $25–75 |
| Website / portal (Vercel Pro) | | $20 |
| Domain, error monitoring | | $1–30 |

**Usage depends on how busy the 100 lines are** (business hours: 10 h × 26 days):

| Average busy | Minutes / month | Usage cost | Numbers + texts + card fees | **Total monthly cost** | Customers that implies | Revenue | **Profit** |
|---|---|---|---|---|---|---|---|
| 10 % | 156,000 | $3,416 | $3,478 | **≈ $7,100–7,300** | ≈ 470 | $60,400 | **≈ $53,000** (88 %) |
| 25 % | 390,000 | $8,541 | $8,694 | **≈ $17,400–17,600** | ≈ 1,170 | $151,100 | **≈ $133,500** (88 %) |
| 50 % | 780,000 | $17,082 | $17,388 | **≈ $34,700–34,900** | ≈ 2,340 | $302,200 | **≈ $267,300** (88 %) |
| 100 % | 1,560,000 | $34,164 | $34,777 | **≈ $69,100–69,300** | ≈ 4,690 | $604,300 | **≈ $535,000** (89 %) |

A peak of 100 simultaneous calls usually means about **10–25 % average** use, so plan for
**≈ $7–18K a month in costs**, covered many times over by the customers needed to generate that
traffic.

**Limits to raise before reaching 100 simultaneous calls** (no extra fee, but they take time):
- **Telnyx:** more simultaneous channels needs the "Verified" account level (identity check).
- **Deepgram:** pay-as-you-go caps how many live streams can run at once. Ask for an increase, or
  move to their Growth plan, which also lowers the per-minute price.
- **OpenAI:** about 1M tokens a minute at 100 calls needs usage tier 3 or higher. Tiers go up
  automatically with spend and account age.
- **Cheaper at volume:** above roughly 100,000 minutes a month, self-hosting speech-to-text and
  the voice on rented GPUs (see `capacity.md` option B), or Deepgram/Telnyx volume pricing, can
  cut the usage cost by 30–50 %.
