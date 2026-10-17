# Capacity and cost: from free testing to 100 simultaneous calls

*Prices are list prices checked in October 2026; treat them as ±20 % and re-check before buying.
Measured numbers come from this codebase on the development laptop (RTX 3050 4 GB, i5-12450H).*

## 1. What one call costs, and where the money goes

A booking call averages about 2–3 minutes. For each **minute** of conversation:

| Part | What drives it | API price | Per call-minute |
|---|---|---|---|
| Phone line | Telnyx inbound/outbound minute + media streaming ($0.0035/min) | ~$0.007–0.010/min | **$0.010** |
| Speech-to-text | Deepgram Nova-3 streaming (or Telnyx-hosted Parakeet $0.0015/min) | $0.005–0.008/min | **$0.006** |
| Text-to-speech | Agent speaks ~450 characters/min; Deepgram Aura-2 $0.030 per 1K chars; **~40 % served from the audio cache** | — | **$0.008** |
| LLM | ~4 turns/min × ~1.2K prompt tokens (compact) or ~2K (cached prefix on OpenAI) | gpt-5.4-mini / Groq paid gpt-oss | **$0.002–0.004** |
| SMS | 1–2 segments per booking (confirmation, reminder) | ~$0.004/segment | **~$0.003** per call |
| **Total** | | | **≈ $0.025–0.030 per minute** (Deepgram path) · **≈ $0.015** (Telnyx-hosted STT/TTS) |

What the platform already does to keep this down:

- **Never pay twice for a sentence.** Every fixed line (greeting, questions, read-back frames, goodbye)
  is synthesised once, pinned in a three-tier cache (memory → disk → shared Supabase bucket) and
  pre-generated when the owner saves the flow. Repeats cost nothing; in testing, repeated lines came
  back from memory in under 0.1 ms.
- **Zero-model turns.** Clean yes/no answers, option answers ("online", "in person", "new patient")
  and every backend-owned question are handled without calling the LLM.
- **Compact prompts.** On free/cheap models a request carries only the active step's brief, facts,
  matching knowledge paragraphs and the last 3 exchanges: about **1,200 tokens** instead of 2,500+.
- **Half-duplex STT.** Caller audio isn't streamed to the paid transcriber while the agent is
  talking (only a short pre-roll for barge-in), which cuts billed STT minutes.

## 2. Free testing phase (now)

These free tiers and trial accounts are for testing only. None of them is used in production or
counted in any cost in this folder.

| Service | Free allowance | What it means |
|---|---|---|
| Groq (LLM: gpt-oss-120b / 20b, qwen) | per model ≈ 8K tokens/min, 200K tokens/day | ~5–6 requests/min per model; 3 models back each other up → a few test calls at a time, a few dozen per day |
| Gemini (LLM 3.1-flash-lite, TTS) | free tier, limits shown in AI Studio | second provider when Groq is busy; TTS fallback |
| Deepgram | $200 credit, no card (user still has to sign up) | ≈ 25–40K STT minutes or ~6M TTS characters |
| Local speech server (laptop GPU) | free, open source | Parakeet STT 80–120 ms/utterance, Kokoro TTS 240–450 ms/sentence, ~2.2 GB VRAM, handled 4 parallel streams fine |
| edge-tts | free, unofficial | last-resort voice for testing only |
| Telnyx | pretrial | calls work; SMS is blocked until the account is upgraded |

The admin panel's **Voice engine** page shows remaining free quota per model and which provider is serving.

## 3. Sizing for 100 simultaneous calls

100 simultaneous calls is a busy deployment: at an average 30 % utilisation across business hours it
is roughly **100,000–150,000 call-minutes per month**.

### Option A — APIs (recommended to launch)

| Buy | Amount | Monthly |
|---|---|---|
| App servers (FastAPI websockets; ~35–50 live calls per 2 vCPU worker) | 3 × 2–4 vCPU / 4 GB | $100–250 |
| Redis (rate limits, concurrency counters) + Postgres (Supabase Pro or similar) | 1 each | $25–75 |
| Telnyx | 100+ concurrent channels (raise the account limit), numbers | usage-based |
| STT/TTS/LLM | usage-based (§1) | 125K min × $0.027 ≈ **$3,400** (Deepgram path) or ≈ **$1,900** (Telnyx-hosted) |

No GPUs to run and it scales to zero at night.

### Option B — self-host speech-to-text and text-to-speech

| Buy | Why | Monthly (24×7) |
|---|---|---|
| 1 × NVIDIA L4 / A10 (24 GB) for Parakeet STT | batched, comfortably 100+ streams | $350–550 |
| 1 × L4 for Kokoro TTS | ~40 speaking at once at peak, fewer with the cache | $350–550 |
| 1 spare GPU (failover) | a dead GPU must not drop calls | $350–550 |
| LLM | stays on an API: a reliable tool-calling LLM for 100 calls needs H100-class GPUs | usage-based |
| App servers + Redis + Postgres | as option A | $125–325 |

**Break-even:** speech APIs cost ≈ $0.014/min (Deepgram STT + TTS after cache). Two or three GPUs ≈
$700–1,650/month, so self-hosting pays off above roughly **60–100K minutes/month** against Deepgram,
and almost never against Telnyx-hosted STT/TTS. It also adds on-call duty (GPU drivers, failover).

**Recommendation:** launch on APIs (option A), keep the provider layer as built so any account or the
whole platform can switch providers from the admin panel, and move speech in-house only past
~100K minutes/month or when a customer requires data to stay on your servers.

## 4. Margins at current prices

| Plan | Price | Included minutes | Revenue / min | Cost / min (API) | Gross margin if fully used |
|---|---|---|---|---|---|
| Starter | $49 | 150 | $0.33 | ~$0.027 | ~92 % |
| Growth | $149 | 600 | $0.25 | ~$0.027 | ~89 % |
| Pro | $349 | 1,800 | $0.19 | ~$0.027 | ~86 % |
| Extra 100 minutes add-on | $25 | 100 | $0.25 | ~$0.027 | ~89 % |

The finance engine (admin → Finance) records the real cost of every call by provider and model
(with a "list price" shadow cost even on free tiers), so these margins can be checked per account.

## 5. Limits to watch as you grow

- **Telnyx concurrent channels:** the trial account allows 2 outbound calls at once. On the paid
  account, raise the limit (the "Verified" level) before marketing.
- **Per-account concurrency:** each tier has `max_concurrent_calls`; extra calls get a polite busy line.
- **LLM rate limits:** paid tiers have far higher limits; set `LLM_ALLOW_PAID=true` and put a paid
  model first in `LLM_CHAIN` for production.
- **One process holds live-call state** (live-call view, in-memory fallbacks). Run several workers
  behind a load balancer with sticky websockets, and keep Redis on for shared counters.
