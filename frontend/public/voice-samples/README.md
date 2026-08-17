# Voice sample clips

Drop one short MP3 per voice tier here. Every card in the Settings → এজেন্ট ও ভয়েস
picker has a ▶ preview button that looks for these exact filenames:

| File | Tier | Engine | Status |
|---|---|---|---|
| `static.mp3` | স্ট্যাটিক কল | Twilio `<Say>` (Google bn-IN WaveNet) | ❌ needs Google creds |
| `nabanita.mp3` | নবনীতা (female, bn-BD) | Azure Neural | ✅ |
| `pradeep.mp3` | প্রদ্বীপ (male, bn-BD) | Azure Neural | ✅ |
| `tanishaa.mp3` | তানিশা (female, bn-IN) | Azure Neural | ✅ |
| `bashkar.mp3` | ভাস্কর (male, bn-IN) | Azure Neural | ✅ |
| `tanishaa_hd.mp3` | তানিশা এইচডি (female, bn-IN) | Azure Dragon HD Omni | ✅ |
| `bashkar_hd.mp3` | ভাস্কর এইচডি (male, bn-IN) | Azure Dragon HD Omni | ✅ |
| `aoede.mp3` | অদিতি (female, bn-IN) | Google Chirp 3 HD | ❌ needs Google creds |
| `puck.mp3` | পার্থ (male, bn-IN) | Google Chirp 3 HD | ❌ needs Google creds |
| `very_basic.mp3` | খুব সাধারণ | Gemini 2.5 Flash TTS | ✅ |
| `basic.mp3` | বেসিক | Gemini 2.5 Pro TTS | ❌ free-tier quota (429) |
| `good.mp3` | ভালো রিজনিং | Gemini 3.1 Flash TTS | ✅ |
| `advance.mp3` | অ্যাডভান্স | ElevenLabs `eleven_v3` | ✅ |

## The script every clip reads

Named voices introduce themselves, then everyone reads the same confirmation line
so merchants can compare like for like:

> এই ভয়েসের নাম {নাম}। আমি {ভারতের/বাংলাদেশের} {মহিলা/পুরুষ} বাংলা ভয়েস।
> আসসালামু আলাইকুম, আমি বাংলাবট থেকে কল করছি। আপনার অর্ডারটি নিশ্চিত করতে চাই।
> আপনি কি অর্ডারটি রিসিভ করবেন?

The quality tiers (খুব সাধারণ / বেসিক / ভালো রিজনিং / অ্যাডভান্স) have no speaker
identity, so they read only the second paragraph.

To regenerate, call each vendor's REST synth endpoint with the text above and save
as MP3 under the tier key. Two gotchas found the hard way:

- **Send Gemini TTS the bare text.** Wrapping it as "say this in X tone: `<text>`"
  makes the model read the line **twice**.
- **Never set SSML style/prosody on the Dragon HD voices** — they reject it.

Until a file exists, the card shows "🔇 এই ভয়েসের স্যাম্পল এখনো যোগ করা হয়নি" the
first time its ▶ is pressed, and stays quiet on later clicks. Keep clips a few
seconds long — they ship with the frontend build (`public/` is copied into `dist/`
as-is).
