/**
 * Small inline-SVG illustrations used across the UI (empty states, page
 * heroes). Inline keeps them theme-consistent (teal palette) and lets the
 * page's Bengali font apply to any embedded text.
 */

import { ReactNode } from "react";

const TEAL = "#0d9488";
const TEAL_DARK = "#0f766e";
const TINT = "#e6f4f2";
const TINT2 = "#99d5cf";

function Frame({ children, label }: { children: ReactNode; label: string }) {
  return (
    <svg viewBox="0 0 140 110" width="140" height="110" role="img" aria-label={label}>
      <ellipse cx="70" cy="96" rx="52" ry="9" fill={TINT} />
      {children}
    </svg>
  );
}

/** Open, empty parcel box — order lists. */
export function BoxArt() {
  return (
    <Frame label="খালি বাক্স">
      <path d="M35 45l35-14 35 14v38l-35 14-35-14z" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" />
      <path d="M35 45l35 14 35-14M70 59v38" fill="none" stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" />
      <path d="M35 45l-12 9 35 15 12-10zM105 45l12 9-35 15-12-10z" fill={TINT} stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" />
      <path d="M60 24c3-6 17-6 20 0" fill="none" stroke={TINT2} strokeWidth="2.5" strokeLinecap="round" strokeDasharray="4 5" />
    </Frame>
  );
}

/** Phone with sound waves — call lists. */
export function CallsArt() {
  return (
    <Frame label="ফোন কল">
      <rect x="48" y="22" width="44" height="72" rx="10" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" />
      <rect x="62" y="28" width="16" height="3.5" rx="1.75" fill={TINT2} />
      <circle cx="70" cy="84" r="4" fill={TINT2} />
      <g transform="translate(70 56)">
        {[10, 18, 26, 18, 10].map((h, i) => (
          <rect key={i} x={(i - 2) * 8 - 2.5} y={-h / 2} width="5" height={h} rx="2.5" fill={i % 2 ? TEAL : TINT2} />
        ))}
      </g>
      <path d="M100 38a18 18 0 0 1 0 24M107 30a30 30 0 0 1 0 40" fill="none" stroke={TINT2} strokeWidth="2.5" strokeLinecap="round" />
    </Frame>
  );
}

/** Chat bubbles — support/ticket lists. */
export function TicketsArt() {
  return (
    <Frame label="সাপোর্ট চ্যাট">
      <rect x="26" y="26" width="58" height="36" rx="10" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" />
      <path d="M38 62l-4 12 16-12z" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" />
      <rect x="36" y="37" width="36" height="4" rx="2" fill={TINT2} />
      <rect x="36" y="47" width="24" height="4" rx="2" fill={TINT} stroke={TINT2} strokeWidth="0.5" />
      <rect x="72" y="52" width="46" height="30" rx="10" fill={TEAL} />
      <path d="M104 82l6 10 2-12z" fill={TEAL} />
      <rect x="80" y="61" width="30" height="4" rx="2" fill="#ffffff" opacity="0.85" />
      <rect x="80" y="70" width="20" height="4" rx="2" fill="#ffffff" opacity="0.55" />
    </Frame>
  );
}

/** Receipt — invoice lists. */
export function InvoicesArt() {
  return (
    <Frame label="ইনভয়েস">
      <path d="M45 20h50v70l-8-6-9 6-8-6-9 6-8-6-8 6z" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" />
      <rect x="55" y="32" width="30" height="4" rx="2" fill={TINT2} />
      <rect x="55" y="42" width="22" height="4" rx="2" fill={TINT} stroke={TINT2} strokeWidth="0.5" />
      <rect x="55" y="52" width="26" height="4" rx="2" fill={TINT} stroke={TINT2} strokeWidth="0.5" />
      <circle cx="98" cy="68" r="16" fill={TEAL} />
      <text x="98" y="75" textAnchor="middle" fontSize="18" fontWeight="700" fill="#ffffff">৳</text>
    </Frame>
  );
}

/** Merchant dashboard greeting: agent with headset. */
export function GreetingArt() {
  return (
    <svg viewBox="0 0 150 120" width="150" height="120" role="img" aria-label="এআই এজেন্ট">
      <circle cx="75" cy="58" r="44" fill={TINT} />
      <circle cx="75" cy="50" r="20" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" />
      <path d="M55 50a20 20 0 0 1 40 0" fill="none" stroke={TEAL_DARK} strokeWidth="4" strokeLinecap="round" />
      <rect x="51" y="46" width="7" height="14" rx="3.5" fill={TEAL_DARK} />
      <rect x="92" y="46" width="7" height="14" rx="3.5" fill={TEAL_DARK} />
      <path d="M95 60c0 8-8 13-16 13" fill="none" stroke={TEAL_DARK} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="77" cy="73" r="3" fill={TEAL_DARK} />
      <circle cx="68" cy="49" r="2.5" fill={TEAL_DARK} />
      <circle cx="82" cy="49" r="2.5" fill={TEAL_DARK} />
      <path d="M68 58c2 3 12 3 14 0" fill="none" stroke={TEAL_DARK} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M42 84c8 12 58 12 66 0l-6 22a8 8 0 0 1-8 6H56a8 8 0 0 1-8-6z" fill={TEAL} />
      <path d="M112 30a16 16 0 0 1 0 22M120 22a28 28 0 0 1 0 38" fill="none" stroke={TINT2} strokeWidth="3" strokeLinecap="round" />
      <circle cx="34" cy="30" r="3.5" fill={TINT2} />
      <circle cx="24" cy="44" r="2.5" fill={TINT2} />
    </svg>
  );
}

/** Wallet with bKash-style coin — billing/payment card. */
export function WalletArt() {
  return (
    <svg viewBox="0 0 140 110" width="120" height="94" role="img" aria-label="পেমেন্ট">
      <ellipse cx="70" cy="98" rx="48" ry="8" fill={TINT} />
      <rect x="28" y="34" width="76" height="52" rx="10" fill="#ffffff" stroke={TEAL} strokeWidth="2.5" />
      <path d="M28 46h76" stroke={TINT2} strokeWidth="2.5" />
      <rect x="84" y="54" width="28" height="18" rx="6" fill={TINT} stroke={TEAL} strokeWidth="2.5" />
      <circle cx="94" cy="63" r="3.5" fill={TEAL} />
      <circle cx="106" cy="34" r="18" fill="#e2136e" />
      <text x="106" y="41" textAnchor="middle" fontSize="17" fontWeight="700" fill="#ffffff">৳</text>
    </svg>
  );
}

/** Finance header: rising chart in a circle. */
export function FinanceArt() {
  return (
    <svg viewBox="0 0 120 100" width="110" height="92" role="img" aria-label="ফাইন্যান্স">
      <circle cx="60" cy="50" r="42" fill={TINT} />
      <rect x="36" y="56" width="10" height="20" rx="3" fill={TINT2} />
      <rect x="52" y="46" width="10" height="30" rx="3" fill={TEAL} />
      <rect x="68" y="36" width="10" height="40" rx="3" fill={TEAL_DARK} />
      <path d="M34 44l18-12 12 6 20-16" fill="none" stroke="#e2136e" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M84 22h4v4" fill="none" stroke="#e2136e" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
