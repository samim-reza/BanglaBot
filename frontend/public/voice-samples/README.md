# Voice sample clips

Drop one short MP3 per voice tier here; the play button on the Settings page
(ভয়েস কোয়ালিটি) looks for these exact filenames:

- `static.mp3` — স্ট্যাটিক কল (keypad prompt voice)
- `very_basic.mp3` — খুব সাধারণ
- `basic.mp3` — সাধারণ
- `good.mp3` — ভালো রিজনিং
- `advance.mp3` — অ্যাডভান্স

Until a file exists, the UI shows "এই ভয়েসের স্যাম্পল এখনো যোগ করা হয়নি"
when its play button is pressed. Keep clips a few seconds long — they ship
with the frontend build (`public/` is copied into `dist/` as-is).
