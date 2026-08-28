/**
 * Tiny landing-page-only i18n. The Bengali source string IS the key, so an
 * untranslated string safely falls back to Bengali. Bangla is the default; the
 * choice is remembered in localStorage under `banglabot_lang`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

export type Lang = "bn" | "en";

export const LANG_KEY = "banglabot_lang";

/** Bengali → English dictionary for every string the landing page renders. */
export const LANDING_EN: Record<string, string> = {
  // nav
  "লগইন": "Log in",
  "ড্যাশবোর্ড খুলুন": "Open dashboard",
  "অ্যাডমিন": "Admin",

  // hero
  "বাংলাদেশের ই-কমার্সের জন্য": "Built for Bangladeshi e-commerce",
  "অর্ডার কনফার্মেশন কল এখন সম্পূর্ণ স্বয়ংক্রিয়": "Order confirmation calls, fully automated",
  "অর্ডার তুলুন — বাকিটা BanglaBot-এর। আমাদের এআই এজেন্ট কাস্টমারকে ফোন করে বাংলায় কথা বলে অর্ডার নিশ্চিত বা বাতিল করে, আর ফলাফল সাথে সাথে আপনার ড্যাশবোর্ডে চলে আসে।":
    "Enter the order — BanglaBot does the rest. Our AI agent calls your customer, speaks Bengali, confirms or cancels the order, and the result lands on your dashboard instantly.",
  "কীভাবে কাজ করে দেখুন": "See how it works",
  "মার্চেন্ট অ্যাকাউন্ট BanglaBot টিম তৈরি করে দেয় — আপনার লগইন তথ্য দিয়ে প্রবেশ করুন।":
    "Merchant accounts are set up by the BanglaBot team — sign in with the credentials you were given.",
  "১০০% বাংলায় কথোপকথন": "Conversations 100% in Bengali",
  "২৪/৭ কল করতে প্রস্তুত": "Ready to call 24/7",
  "রিয়েল-টাইম ফলাফল": "Real-time results",

  // how it works
  "যেভাবে কাজ করে": "How it works",
  "অর্ডার যোগ করুন": "Add the order",
  "ড্যাশবোর্ডে কাস্টমারের নাম, ফোন আর পণ্য লিখুন — ব্যস।": "Type the customer's name, phone and items into the dashboard — that's it.",
  "এআই কল করে": "The AI calls",
  "BanglaBot কাস্টমারকে ফোন করে বাংলায় অর্ডারের বিবরণ শুনিয়ে নিশ্চিত হতে বলে।":
    "BanglaBot phones the customer, reads back the order in Bengali and asks them to confirm.",
  "ফলাফল সাথে সাথে": "Instant outcome",
  "নিশ্চিত, বাতিল বা রিভিউ দরকার — স্ট্যাটাস, রেকর্ডিং ও ট্রান্সক্রিপ্টসহ ড্যাশবোর্ডে আপডেট।":
    "Confirmed, cancelled or needs review — the status updates with the recording and transcript.",

  // features
  "যা যা পাচ্ছেন": "Everything you get",
  "বাংলা এআই ভয়েস এজেন্ট": "Bengali AI voice agent",
  "স্বাভাবিক বাংলায় কথা বলে, কাস্টমারের প্রশ্নের উত্তর দেয়।": "Speaks natural Bengali and answers your customer's questions.",
  "কল রেকর্ডিং ও ট্রান্সক্রিপ্ট": "Call recording & transcript",
  "প্রতিটি কল পরে শোনা যায়, লিখিত রূপসহ।": "Listen to every call later, with a written transcript.",
  "লাইভ ড্যাশবোর্ড": "Live dashboard",
  "কোন অর্ডার নিশ্চিত, কোনটা বাতিল — এক নজরে।": "Which orders confirmed, which cancelled — at a glance.",
  "হিউম্যান ট্রান্সফার": "Human transfer",
  "কাস্টমার মানুষ চাইলে কলটি আপনার সাপোর্ট নম্বরে চলে যায়।":
    "If the customer asks for a person, the call transfers to your support number.",
  "RTO কমান": "Cut RTO losses",
  "ভুয়া অর্ডার আগে থেকেই বাদ দিন — কুরিয়ার খরচ বাঁচান।": "Weed out fake orders before dispatch — save courier costs.",
  "বাংলা + ইংরেজি": "Bangla + English",
  "কাস্টমার যে ভাষায় স্বচ্ছন্দ, এজেন্ট সেই ভাষাতেই কথা বলে — বাংলা বা ইংরেজি।":
    "The agent speaks whichever language the customer is comfortable in — Bangla or English.",

  // FAQ
  "সাধারণ প্রশ্ন": "Common questions",
  "কল কি সত্যিই বাংলায় হয়?": "Are the calls really in Bengali?",
  "হ্যাঁ — এজেন্ট সম্পূর্ণ বাংলায় কথা বলে, কাস্টমারের উত্তরও বাংলাতেই বোঝে।":
    "Yes — the agent speaks entirely in Bengali and understands the customer's Bengali replies.",
  "নম্বর কোথা থেকে আসে?": "Which number do calls come from?",
  "কলগুলো আমাদের প্ল্যাটফর্ম নম্বর থেকে যায়; কাস্টমার মানুষ চাইলে আপনার সাপোর্ট নম্বরে ট্রান্সফার হয়।":
    "Calls go out from our platform number; if the customer wants a person, we transfer to your support line.",
  "কাস্টমার ফোন না ধরলে কী হয়?": "What happens if the customer doesn't answer?",
  "অর্ডারটি 'নো আনসার' স্ট্যাটাসে চলে যায়; ড্যাশবোর্ড থেকে যেকোনো সময় আবার কল দিতে পারবেন।":
    "The order is marked no-answer; you can call it again any time from the dashboard.",

  // CTA & footer
  "আজই BanglaBot দিয়ে অর্ডার কনফার্ম করা শুরু করুন": "Start confirming orders with BanglaBot today",
  "ড্যাশবোর্ডে লগইন করুন": "Log in to the dashboard",
  "প্ল্যাটফর্ম অ্যাডমিন?": "Platform operator?",
  "অ্যাডমিন লগইন": "Admin login",
};

const BN_DIGITS = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];

/** Translate a Bengali source string; `{key}` placeholders are filled from vars. */
export function translate(lang: Lang, bn: string, vars?: Record<string, string | number>): string {
  let s = lang === "bn" ? bn : (LANDING_EN[bn] ?? bn);
  if (vars) {
    for (const [key, v] of Object.entries(vars)) {
      s = s.split(`{${key}}`).join(String(v));
    }
  }
  return s;
}

/** Format a number with Bengali digits when the UI is in Bangla. Deterministic (no Intl) so SSR and client agree. */
export function fmtNum(lang: Lang, n: number | string): string {
  const str = String(n);
  if (lang !== "bn") return str;
  return str.replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)]);
}

export function readStoredLang(): Lang {
  try {
    return window.localStorage.getItem(LANG_KEY) === "en" ? "en" : "bn";
  } catch {
    return "bn";
  }
}

/**
 * Landing-local language state. Always renders Bangla on the server and on the
 * first client render, then switches to the stored choice after mount so there
 * is never a hydration mismatch.
 */
export function useLandingLang() {
  const [lang, setLangState] = useState<Lang>("bn");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setLangState(readStoredLang());
    setMounted(true);
  }, []);

  const setLang = useCallback((next: Lang) => {
    try {
      window.localStorage.setItem(LANG_KEY, next);
    } catch {
      // storage unavailable — keep the in-memory choice
    }
    setLangState(next);
  }, []);

  const toggle = useCallback(() => setLang(lang === "bn" ? "en" : "bn"), [lang, setLang]);

  const t = useCallback((bn: string, vars?: Record<string, string | number>) => translate(lang, bn, vars), [lang]);
  const num = useCallback((n: number | string) => fmtNum(lang, n), [lang]);

  return useMemo(() => ({ lang, mounted, setLang, toggle, t, fmtNum: num }), [lang, mounted, setLang, toggle, t, num]);
}
