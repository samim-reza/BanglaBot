# BanglaBot — Cost Analysis (BDT, Aug 2026)

Every vendor in the stack, every model we can select, and the cost of each
combination. All figures at **৳123 / USD**.

The production stack is **local BD telephony (Alap/BTCL/IPTSP) + a per-tier TTS
engine (Azure / Gemini / ElevenLabs) + OpenAI** `gpt-5.4-mini` **and**
`gpt-4o-mini-transcribe`. A typical confirmation call runs **1–1.5 minutes**.

---

## 1. Unit conversions (read this first)

Vendors bill in three different units. Everything below is normalised to them:


| Unit                               | Value                           | Why                                                                                                            |
| ---------------------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **1 minute of synthesized speech** | **≈ 900 Bengali characters**    | ~130–150 wpm at default rate; Bangla words average ~6 chars                                                    |
| **1 minute of synthesized speech** | **= 1,500 Gemini audio tokens** | Gemini bills audio at 25 tokens/sec (cross-checked: Live API lists $12.00/1M *and* $0.018/min → 1,500 tok/min) |
| **Bot talk ratio**                 | **~40% of connected time**      | The rest is the customer speaking, silence, and dial tone — none of it billed by the TTS vendor                |


So **1 connected minute ≈ 360 synthesized characters ≈ 600 audio tokens**, and
≈ 0.4 min of customer speech to transcribe.

Two columns appear throughout:

- **৳/audio-min** — cost per minute of audio the engine actually produces. Use this to compare engines.
- **৳/conn-min** — cost per minute of *connected call*, at the 40% talk ratio. Use this to build a call price.

> Azure and ElevenLabs bill **every character including spaces, punctuation and
> SSML markup** (except `<speak>`/`<voice>`). Trimming the script is the single
> biggest lever on TTS cost.

---



## 2. Telephony (per connected minute)


| Route                                      | Rate                                   | ৳ / conn-min | Billing granularity            |
| ------------------------------------------ | -------------------------------------- | ------------ | ------------------------------ |
| **Alap / BTCL**                            | 35 paisa/min + VAT                     | **৳0.40**    | 1-second pulse                 |
| Local IPTSP trunk (Amber IT / ADN / Link3) | ৳0.40–0.70/min                         | ৳0.40–0.70   | usually 1-sec                  |
| Twilio → Bangladesh                        | $0.060/min + $0.0044/min media streams | **৳7.92**    | **rounds up to whole minutes** |


Twilio's rounding is worse than it looks: a 70-second call bills 2 minutes →
**effective ~৳9.5/min** on typical short calls. Unanswered calls cost ≈ nothing
on either route.

**Alap is 20× cheaper than Twilio and is the whole reason the unit economics work.**
See §9 for the caveats on actually wiring it up.

---



## 3. Text-to-speech engines



### 3a. Azure Speech — Neural voices

Used by the four named Bengali speaker tiers (`bn-BD-Nabanita`, `bn-BD-Pradeep`,
`bn-IN-Tanishaa`, `bn-IN-Bashkar`). Billed per character.


| Plan                        | $/1M chars | ৳/audio-min | ৳/conn-min | Break-even volume       |
| --------------------------- | ---------- | ----------- | ---------- | ----------------------- |
| **Pay-as-you-go (Neural)**  | $16.00     | ৳1.77       | **৳0.71**  | — (500K chars/mo free)  |
| Commitment 80M ($960/mo)    | $12.00     | ৳1.33       | ৳0.53      | 60M chars/mo            |
| Commitment 400M ($3,900/mo) | $9.75      | ৳1.08       | ৳0.43      | 244M chars/mo           |
| Commitment 2B ($15,000/mo)  | $7.50      | ৳0.83       | ৳0.33      | 938M chars/mo           |
| Commitment 4B ($25,600/mo)  | $6.40      | ৳0.71       | ৳0.28      | 1.6B chars/mo           |
| Neural **HD** voices (PAYG) | $22.00     | ৳2.44       | ৳0.97      | —                       |
| Custom professional voice   | $24.00     | ৳2.66       | ৳1.06      | + training/hosting fees |


**Bengali HD availability:** Dragon HD Omni ships only `bn-IN-Tanishaa` and
`bn-IN-Bashkar` — **there is no bn-BD HD pair**, so HD is Indian Bengali only.
HD voices also reject several SSML elements, so never set style/prosody on them.

- Overage on every commitment tier is charged at **the same rate as the commitment**
($960/80M = $12.00, $15,000/2B = $7.50), so going over costs nothing extra —
the only risk is *under*-using a prepaid block.
- First month is pro-rated (cost and quota) by days remaining.
- **Stay on pay-as-you-go.** The smallest commitment needs ~60M chars/month to break
even = ~67,000 minutes of bot speech ≈ 44,000 three-minute calls/month.
- Output sample rate (we use 16 kHz) does **not** affect billing — only character count does.



### 3b. Google Gemini TTS

Used by the `very_basic`, `basic` and `good` tiers. Billed in tokens: text in,
audio out.


| Model                                          | $/1M in | $/1M out | ৳/audio-min | ৳/conn-min |
| ---------------------------------------------- | ------- | -------- | ----------- | ---------- |
| `gemini-2.5-flash-preview-tts`                 | $0.50   | $10.00   | ৳1.87       | **৳0.75**  |
| `gemini-2.5-pro-preview-tts`                   | $1.00   | $20.00   | ৳3.75       | ৳1.50      |
| `gemini-3.1-flash-tts-preview`                 | $1.00   | $20.00   | ৳3.75       | ৳1.50      |
| *…same, Batch API (not usable for live calls)* | half    | half     | ৳1.88       | ৳0.75      |


Input text is ~2% of the bill — the audio output tokens are essentially the whole cost.

> ⚠️ `gemini-2.5-pro-preview-tts` and `gemini-3.1-flash-tts-preview` cost **exactly
> the same** ($20/1M out), but our tier catalog bills them at ×1.5 and ×2.0. See §7.



### 3c. ElevenLabs

Used by the `advance` tier. Billed in credits; on `eleven_v3` and
`multilingual_v2` **1 character = 1 credit**. Flash/Turbo models are ~0.5 credits/char.


| Plan / model                   | Effective $/1M chars | ৳/audio-min | ৳/conn-min | Monthly quota                           |
| ------------------------------ | -------------------- | ----------- | ---------- | --------------------------------------- |
| Free                           | —                    | —           | —          | **unusable** — API TTS returns HTTP 402 |
| Starter $6                     | ~$0.20/1k            | —           | —          | 30k credits (~83 conn-min)              |
| **Creator $22**                | $181.82              | ৳20.13      | **৳8.05**  | 121k credits (~336 conn-min)            |
| **Pro $99**                    | $165.00              | ৳18.27      | **৳7.31**  | 600k credits (~1,667 conn-min)          |
| **Scale $299**                 | $166.11              | ৳18.39      | ৳7.36      | 1.8M credits (~5,000 conn-min)          |
| API overage, v3                | $100.00              | ৳11.07      | ৳4.43      | pay-per-use                             |
| ~~API overage, Flash / Turbo~~ | ~~$50.00~~           | —           | —          | **no Bengali — unusable**               |


- 🚫 `eleven_v3` **is the only ElevenLabs model that speaks Bengali.**
`multilingual_v2` covers 29 languages and `flash_v2_5` / `turbo_v2_5` 32 — Bengali is
in none of those lists; only v3's 70+ language set includes it (`ben`). So the
half-price Flash/Turbo rate is **not** available to us, and there is no cheaper
ElevenLabs path. Don't "optimize" the `advance` tier to a cheaper model.
- **Pro is marginally cheaper per credit than Scale** ($0.000165 vs $0.000166). Scale
only wins because of its larger quota and 3 seats — buy on quota, not on unit price.
- ElevenLabs is **~10× Azure and ~11× Gemini Flash TTS** per character. On the local
telephony stack it dominates the bill entirely.



### 3d. Google Cloud TTS

Used by the `aoede` / `puck` tiers. Billed per character; **bn-IN only** (Google has
no bn-BD locale).


| Voice class                           | $/1M chars | ৳/audio-min | ৳/conn-min | Free tier   |
| ------------------------------------- | ---------- | ----------- | ---------- | ----------- |
| **Chirp 3: HD** (`bn-IN-Chirp3-HD-`*) | $30.00     | ৳3.32       | **৳1.33**  | 1M chars/mo |
| WaveNet (`bn-IN-Wavenet-*`)           | $16.00     | ৳1.77       | ৳0.71      | 1M chars/mo |
| Standard (`bn-IN-Standard-*`)         | $4.00      | ৳0.44       | **৳0.18**  | 4M chars/mo |


The 1M chars/month free tier is worth ~2,800 connected minutes — at 10 merchants
(§10) that covers **62% of all synthesis for free**, which makes Chirp 3 HD much
cheaper in practice than its sticker rate suggests.

### 3e. TTS engines side by side (৳ per connected minute)


| Google Standard | Azure Neural | Gemini 2.5 Flash TTS | Azure HD | Google Chirp 3 HD | Gemini Pro / 3.1 TTS | ElevenLabs v3 |
| --------------- | ------------ | -------------------- | -------- | ----------------- | -------------------- | ------------- |
| ৳0.18           | **৳0.71**    | ৳0.75                | ৳0.97    | ৳1.33             | ৳1.50                | ৳7.31         |


---



## 4. Speech-to-text


| Model                                         | Rate                                | ৳ / conn-min (40% customer speech) |
| --------------------------------------------- | ----------------------------------- | ---------------------------------- |
| **OpenAI** `gpt-4o-mini-transcribe` (current) | $0.003/min of audio                 | **৳0.15**                          |
| OpenAI `gpt-4o-transcribe`                    | $0.006/min                          | ৳0.30                              |
| Gemini 2.5 Flash (audio input)                | $1.00/1M audio tokens = $0.0015/min | ৳0.07                              |


---



## 5. LLM (the conversation brain)

Assumes ~4 turns per connected minute, ~1,500 tokens of context per turn
(≈6,000 input tok/min) and ~60 output tokens per turn (≈240 out/min).


| Model                               | $/1M in | $/1M out | ৳ / conn-min |
| ----------------------------------- | ------- | -------- | ------------ |
| **OpenAI** `gpt-5.4-mini` (current) | $0.75   | $4.50    | **৳0.69**    |
| Gemini 3.6 Flash                    | $0.75   | $3.75    | ৳0.66        |
| Gemini 2.5 Flash                    | $0.30   | $2.50    | ৳0.30        |
| Gemini 3.1 Flash-Lite               | $0.25   | $1.50    | ৳0.23        |
| Gemini 2.5 Flash-Lite               | $0.10   | $0.40    | **৳0.09**    |


**Combined "brain" (STT + LLM) per connected minute:**


| Brain                                 | ৳ / conn-min |
| ------------------------------------- | ------------ |
| OpenAI STT + `gpt-5.4-mini` (current) | **৳0.84**    |
| OpenAI STT + Gemini 2.5 Flash         | ৳0.45        |
| OpenAI STT + Gemini 2.5 Flash-Lite    | ৳0.24        |




### 5b. The all-in-one alternative: Gemini Live (native audio)

`gemini-3.1-flash-live-preview` replaces STT + LLM + TTS with one speech-to-speech
model — no transcription hop, much lower latency.


| Component                        | Rate       | ৳ / conn-min |
| -------------------------------- | ---------- | ------------ |
| Audio input (full call duration) | $0.005/min | ৳0.62        |
| Audio output (40% bot talk)      | $0.018/min | ৳0.89        |
| **Total, replaces STT+LLM+TTS**  |            | **৳1.50**    |


Compare to the current pipeline's cheapest path (Azure TTS ৳0.71 + brain ৳0.84 =
**৳1.55**) — Live is a wash on cost but wins on latency. The open question is
whether its Bengali output quality matches Azure's `bn-BD` neural voices; it also
means re-plumbing the Pipecat pipeline away from the STT→LLM→TTS chain.

---



## 6. The combination matrix

**Total ৳ per connected minute = telephony + TTS + STT + LLM.**
Brain = OpenAI STT + `gpt-5.4-mini` (৳0.84) unless noted.

### On Alap / BTCL (৳0.40/min) — production


| #   | Combination                                                | Telephony | TTS  | Brain | **Total ৳/min** | ৳/call (1.25 min) |
| --- | ---------------------------------------------------------- | --------- | ---- | ----- | --------------- | ----------------- |
| 1   | **Alap + Azure Neural PAYG**                               | 0.40      | 0.71 | 0.84  | **৳1.95**       | ৳2.44             |
| 2   | Alap + Azure Neural + cheap brain (Flash-Lite)             | 0.40      | 0.71 | 0.24  | **৳1.35**       | ৳1.69             |
| 3   | Alap + Azure @ 2B commitment                               | 0.40      | 0.33 | 0.84  | ৳1.57           | ৳1.96             |
| 4   | **Alap + Gemini 2.5 Flash TTS**                            | 0.40      | 0.75 | 0.84  | **৳1.99**       | ৳2.49             |
| 5   | Alap + Gemini 2.5 Pro TTS                                  | 0.40      | 1.50 | 0.84  | ৳2.74           | ৳3.43             |
| 6   | Alap + Gemini 3.1 Flash TTS                                | 0.40      | 1.50 | 0.84  | ৳2.74           | ৳3.43             |
| 7   | Alap + Gemini Live (native audio, no separate STT/LLM/TTS) | 0.40      | —    | 1.50  | **৳1.90**       | ৳2.38             |
| 8   | Alap + ElevenLabs Flash/Turbo                              | 0.40      | 2.21 | 0.84  | ৳3.45           | ৳4.31             |
| 9   | Alap + ElevenLabs v3 (Pro plan)                            | 0.40      | 7.31 | 0.84  | **৳8.55**       | ৳10.69            |
| 10  | Alap + ElevenLabs v3 (Creator plan)                        | 0.40      | 8.05 | 0.84  | ৳9.29           | ৳11.61            |
| 11  | Alap + **static/keypad** (no AI at all)                    | 0.40      | —    | —     | **৳0.40**       | ৳0.50             |




### On Twilio (৳7.92/min) — current dev setup

Add **৳7.52** to every row above:


| #   | Combination                         | **Total ৳/min** | ৳/call (1.25 min, 2-min rounding) |
| --- | ----------------------------------- | --------------- | --------------------------------- |
| 1   | Twilio + Azure Neural PAYG          | **৳9.47**       | ৳17.4                             |
| 4   | Twilio + Gemini 2.5 Flash TTS       | ৳9.51           | ৳17.5                             |
| 5–6 | Twilio + Gemini Pro / 3.1 Flash TTS | ৳10.26          | ৳18.5                             |
| 7   | Twilio + Gemini Live                | ৳9.42           | ৳17.3                             |
| 8   | Twilio + ElevenLabs Flash           | ৳10.97          | ৳19.0                             |
| 9   | Twilio + ElevenLabs v3 (Pro)        | **৳16.07**      | ৳25.8                             |
| 11  | Twilio + static/keypad              | ৳7.92           | ৳15.8                             |


**On Twilio the AI stack is noise — telephony is 50–84% of the bill.** On Alap the
opposite is true, and TTS choice becomes the dominant decision.

**Cheapest viable AI call: ৳1.35/min** (Alap + Azure + Flash-Lite brain).
**Most expensive: ৳16.07/min** (Twilio + ElevenLabs v3) — a **12× spread**.

---



## 7. What each merchant-facing voice tier actually costs

From `backend/app/services/voice_tiers.py`, on the Alap stack:


| Tier (merchant sees)            | Engine                 | Accent | Real ৳/min | Multiplier | Merchant pays* | Margin |
| ------------------------------- | ---------------------- | ------ | ---------- | ---------- | -------------- | ------ |
| স্ট্যাটিক কল                    | Twilio `<Say>`, keypad | —      | ৳0.40      | ×0.5       | ৳10            | 96%    |
| নবনীতা / প্রদ্বীপ               | Azure Neural           | bn-BD  | ৳1.95      | ×1.0       | ৳20            | 90%    |
| তানিশা / ভাস্কর                 | Azure Neural           | bn-IN  | ৳1.95      | ×1.0       | ৳20            | 90%    |
| খুব সাধারণ                      | Gemini 2.5 Flash TTS   | —      | ৳1.99      | ×1.0       | ৳20            | 90%    |
| **তানিশা এইচডি / ভাস্কর এইচডি** | Azure Dragon HD Omni   | bn-IN  | ৳2.21      | ×1.25      | ৳25            | 91%    |
| **অদিতি / পার্থ**               | Google Chirp 3 HD      | bn-IN  | ৳2.57      | ×1.5       | ৳30            | 91%    |
| বেসিক                           | Gemini 2.5 Pro TTS     | —      | ৳2.74      | ×1.5       | ৳30            | 91%    |
| ভালো রিজনিং                     | Gemini 3.1 Flash TTS   | —      | ৳2.74      | ×2.0       | ৳40            | 93%    |
| অ্যাডভান্স                      | ElevenLabs `eleven_v3` | —      | ৳8.55      | ×2.5       | ৳50            | 83%    |


 At the Business package rate of ৳20 per plan-minute (§11).

**Three things to fix in the tier catalog:**

1. `basic` **(×1.5) and** `good` **(×2.0) cost identically** — both Gemini models are
  $20/1M output tokens. Either move `good` to a genuinely better engine or collapse
   the two multipliers.
2. `advance` **is under-priced relative to cost.** It is 4.4× the Azure tiers' cost but
  only ×2.5 on the multiplier. ×3.5 would restore parity. There is **no cheaper
   ElevenLabs option** — see §3c.
3. **Only 2 of the 8 named voices are Bangladeshi Bengali.** Everything HD (Azure HD,
  Google Chirp 3) is bn-IN, so merchants who want the higher-quality voices are pushed
   onto an Indian accent. If BD accent matters for answer rates, the bn-BD neural pair
   (নবনীতা / প্রদ্বীপ) has to stay the default — which it is.

---



## 8. Fixed monthly costs


| Item                   | Plan               | ৳ / month    |
| ---------------------- | ------------------ | ------------ |
| VPS (app + SIP bridge) | $18                | ৳2,214       |
| Supabase               | $15                | ৳1,845       |
| SIP trunk line rent    | provider-dependent | ~৳500 (est.) |
| **Fixed base**         |                    | **≈ ৳4,600** |


TTS/STT/LLM subscriptions are usage-based (§3–5) except ElevenLabs, which is a
prepaid monthly plan — pick the plan from the quota column in §3c.

---



## 9. Caveats on the Alap / BTCL route

1. **The consumer Alap app can't be wired into this backend.** You need a business SIP
  trunk (BTCL IP Telephony, or an IPTSP like Amber IT / ADN / Link3 — similar
   ৳0.40–0.70/min rates), plus a SIP↔media bridge (Asterisk/FreeSWITCH) in front of the
   Pipecat pipeline — Pipecat's telephony serializers speak Twilio/Telnyx-style
   websockets, not raw SIP. Roughly 1–2 weeks of one-time engineering.
2. **Regulatory:** automated outbound calls from a +880 business number fall under BTRC
  telemarketing rules (caller-ID registration, calling-hour limits). Upside: a local
   +880 caller ID gets answered far more often than a foreign number.

---



## 10. Volume scenarios

**Planning assumption:** an average paying merchant does 12 orders/day ≈ 360 orders/month
≈ **450 connected minutes/month** (1.25 min/call, ~85% answer rate — unanswered
redials cost ≈ nothing). Reported benchmark: an established small BD Facebook page
does ~25 orders/day; most active pages do less.

### 10 merchants = 3,600 calls ≈ 4,500 connected minutes/month

That is **1.62M synthesized characters / 2.7M Gemini audio tokens per month.**


| Stack                             | Telephony | TTS     | Brain  | Fixed  | **Total ৳/mo** | ৳/min | ৳/order |
| --------------------------------- | --------- | ------- | ------ | ------ | -------------- | ----- | ------- |
| **Alap + Azure PAYG**             | ৳2,070    | ৳3,188  | ৳3,780 | ৳4,600 | **৳13,638**    | ৳3.0  | ৳3.8    |
| Alap + Gemini 2.5 Flash TTS       | ৳2,070    | ৳3,375  | ৳3,780 | ৳4,600 | ৳13,825        | ৳3.1  | ৳3.8    |
| Alap + Gemini Live                | ৳2,070    | —       | ৳6,750 | ৳4,600 | ৳13,420        | ৳3.0  | ৳3.7    |
| Alap + ElevenLabs v3 (Scale $299) | ৳2,070    | ৳36,777 | ৳3,780 | ৳4,600 | **৳47,227**    | ৳10.5 | ৳13.1   |
| Twilio + ElevenLabs v3 (Scale)    | ৳35,640   | ৳36,777 | ৳3,780 | ৳4,600 | ৳80,797        | ৳18.0 | ৳22.4   |


At this volume **Azure stays on pay-as-you-go by a wide margin** (1.62M vs the
60M chars needed to justify the smallest commitment), and **ElevenLabs alone costs
2.7× the entire rest of the business.**

Revenue at 10 merchants on the Business package = ৳130,000/month.


|                         | Azure stack        | ElevenLabs stack  |
| ----------------------- | ------------------ | ----------------- |
| Revenue (10 × Business) | ৳130,000           | ৳130,000          |
| Costs                   | ৳13,638            | ৳47,227           |
| **Gross profit**        | **৳116,362 (90%)** | **৳82,773 (64%)** |




### 100 merchants ≈ 45,000 connected minutes/month

16.2M chars/month. Still below Azure's 80M break-even (still PAYG). Costs scale
roughly linearly: **≈ ৳96,000/mo** on the Azure stack against ৳1.3M revenue.

---



## 11. Recommended merchant pricing (per plan-minute)


| Package                                       | Price / mo | Included minutes | Effective ৳/min | Extra minutes |
| --------------------------------------------- | ---------- | ---------------- | --------------- | ------------- |
| Trial                                         | ৳0         | 25 (7 days)      | —               | —             |
| Starter                                       | ৳3,000     | 125              | ৳24             | ৳28           |
| Growth                                        | ৳7,000     | 320              | ৳22             | ৳25           |
| **Business** (fits the avg. 450-min customer) | ৳13,000    | 650              | ৳20             | ৳22           |


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

---



## 12. Cost levers, in order of impact

1. **Get off Twilio.** ৳7.52/min saved — bigger than the entire AI stack.
2. **Price** `advance` **at ×3.5,** or drop it. ElevenLabs is ~10× every alternative per
  character and `eleven_v3` is the only model of theirs that speaks Bengali, so there
   is no cheaper way to keep the tier.
3. **Shorten the script.** Azure/ElevenLabs bill every character including spaces and
  SSML. A 20% shorter prompt is a 20% smaller TTS bill.
4. **Cache the greeting audio.** The opening line is identical on every call and is
  currently re-synthesized each time.
5. **Move the LLM to Gemini 2.5 Flash-Lite** — ৳0.60/min saved vs `gpt-5.4-mini`, if
  Bengali reasoning quality holds.
6. **Ignore Azure commitment tiers** until ~44,000 calls/month.

---



## 13. Assumptions & sources

- Exchange rate ৳123/USD (mid-market, Aug 2026).
- Speech rate 900 Bengali chars/audio-minute; bot talk ratio 40% of connected time.
Both are estimates — measure against real call logs and revise.
- **Azure Speech:** Neural $16/1M chars, HD $22/1M, custom $24/1M; commitment tiers
$960/80M, $3,900/400M, $15,000/2B, $25,600/4B —
[azure.microsoft.com/pricing/details/speech](https://azure.microsoft.com/en-us/pricing/details/speech/).
Billable-character rules (spaces, punctuation, SSML markup; CJK counts double) —
[learn.microsoft.com](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech).
- **Gemini:** TTS and text model pricing, Live API audio rates —
[ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing).
- **ElevenLabs:** Creator $22/121k credits, Pro $99/600k, Scale $299/1.8M; 1 credit/char
on v3; API overage $0.10/1k chars —
[flexprice.io](https://flexprice.io/blog/elevenlabs-pricing-breakdown),
[layer3labs.io](https://www.layer3labs.io/guides/elevenlabs-pricing).
**Bengali is supported only by** `eleven_v3` (70+ languages); multilingual v2 (29) and
Flash/Turbo v2.5 (32) exclude it —
[elevenlabs.io/docs](https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support).
**Free plan can't be used** — API TTS with library voices requires a paid plan (verified: HTTP 402).
- **Google Cloud TTS:** Chirp 3 HD $30/1M chars (1M free/mo), WaveNet $16/1M, Standard
$4/1M; bn-IN supported, no bn-BD locale —
[cloud.google.com/text-to-speech/pricing](https://cloud.google.com/text-to-speech/pricing),
[Chirp 3 HD docs](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd).
- **Azure Dragon HD Omni:** bn-IN Tanishaa and Bashkar only, no bn-BD —
[Dragon HD Omni voice list](https://github.com/Azure-Samples/Cognitive-Speech-TTS/blob/master/Blog-Samples/Introducing-Dragon-HD-Omni/dragonhdomni_voice_list.json).
- **OpenAI:** `gpt-5.4-mini` $0.75/M in, $4.50/M out — [openrouter.ai](https://openrouter.ai/openai/gpt-5.4-mini);
`gpt-4o-mini-transcribe` ≈ $0.003/min — [costgoat.com](https://costgoat.com/pricing/openai-transcription).
- **Twilio → BD:** $0.060/min + $0.0044/min media streams, per-minute rounding —
[twilio.com/voice/pricing/bd](https://www.twilio.com/en-us/voice/pricing/bd).
- **Alap (BTCL):** 35 paisa/min + VAT ≈ 40 paisa, 1-second pulse —
[businessinspection.com.bd](https://businessinspection.com.bd/btcls-alaap-app-revolutionary-solution-for-affordable-calling/);
IPTSP business trunks ৳0.40–0.70/min.
- **F-commerce order volume:** established small pages ~25 orders/day; planning assumption
12 orders/day per paying merchant —
[thedailystar.net](https://www.thedailystar.net/business/news/f-commerce-saviour-amid-pandemic-woes-2017061),
[tbsnews.net](https://www.tbsnews.net/economy/facebook-restriction-keeps-f-commerce-entrepreneurs-bay-905416).
- **Not included:** your own time, payment-gateway fees (~2–3%), marketing, Twilio's
own `<Say>` surcharge for non-basic neural voices on static calls (unverified rate).



