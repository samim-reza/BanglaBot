import { ReactNode, createContext, useCallback, useContext, useMemo, useState } from "react";
import { EN } from "./en";

export type Lang = "bn" | "en";

const LANG_KEY = "banglabot_lang";

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Translate a Bengali source string; `{key}` placeholders are filled from vars. */
  t: (bn: string, vars?: Record<string, string | number>) => string;
  fmtNum: (n: number | string) => string;
  fmtMoney: (n: number | string) => string;
  fmtDate: (d: string | Date) => string;
  fmtDateTime: (d: string | Date) => string;
}

const LangContext = createContext<LangContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem(LANG_KEY);
    return saved === "en" ? "en" : "bn";
  });

  const setLang = useCallback((next: Lang) => {
    localStorage.setItem(LANG_KEY, next);
    document.documentElement.lang = next;
    setLangState(next);
  }, []);

  const value = useMemo<LangContextValue>(() => {
    const locale = lang === "bn" ? "bn-BD" : "en-US";
    const t = (bn: string, vars?: Record<string, string | number>) => {
      let s = lang === "bn" ? bn : EN[bn] ?? bn;
      if (vars) {
        for (const [key, v] of Object.entries(vars)) {
          s = s.split(`{${key}}`).join(String(v));
        }
      }
      return s;
    };
    return {
      lang,
      setLang,
      t,
      fmtNum: (n) => Number(n).toLocaleString(locale),
      fmtMoney: (n) => `৳${Number(n).toLocaleString(locale)}`,
      fmtDate: (d) => new Date(d).toLocaleDateString(locale),
      fmtDateTime: (d) => new Date(d).toLocaleString(locale),
    };
  }, [lang, setLang]);

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used inside LanguageProvider");
  return ctx;
}

/** Small pill button that flips the UI language. */
export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <button
      type="button"
      className="lang-toggle"
      onClick={() => setLang(lang === "bn" ? "en" : "bn")}
      title={lang === "bn" ? "Switch to English" : "বাংলায় দেখুন"}
    >
      {lang === "bn" ? "EN" : "বাং"}
    </button>
  );
}
