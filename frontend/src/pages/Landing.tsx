import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, auth } from "../api/client";
import { Plan } from "../api/types";
import HeroArt from "../components/HeroArt";
import { LangToggle, useLang } from "../i18n";

interface PublicPlatform {
  platform_name: string;
  support_email: string;
  support_phone: string;
  bkash_number: string;
  signup_enabled: boolean;
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="26"
      height="26"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  );
}

const FEATURES: { icon: ReactNode; title: string; desc: string }[] = [
  {
    icon: (
      <Icon>
        <path d="M12 3a4 4 0 0 1 4 4v4a4 4 0 0 1-8 0V7a4 4 0 0 1 4-4z" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
      </Icon>
    ),
    title: "বাংলা এআই ভয়েস এজেন্ট",
    desc: "স্বাভাবিক বাংলায় কথা বলে, কাস্টমারের প্রশ্নের উত্তর দেয়।",
  },
  {
    icon: (
      <Icon>
        <path d="M4 12h2l2-6 4 12 3-8 2 2h3" />
        <circle cx="12" cy="12" r="10" />
      </Icon>
    ),
    title: "কল রেকর্ডিং ও ট্রান্সক্রিপ্ট",
    desc: "প্রতিটি কল পরে শোনা যায়, লিখিত রূপসহ।",
  },
  {
    icon: (
      <Icon>
        <rect x="3" y="4" width="18" height="14" rx="2" />
        <path d="M7 14l3-3 2 2 4-4M3 21h18" />
      </Icon>
    ),
    title: "লাইভ ড্যাশবোর্ড",
    desc: "কোন অর্ডার নিশ্চিত, কোনটা বাতিল — এক নজরে।",
  },
  {
    icon: (
      <Icon>
        <circle cx="9" cy="8" r="3.5" />
        <path d="M3 20a6 6 0 0 1 12 0M16 4.5a4 4 0 0 1 0 7M19 3a7.5 7.5 0 0 1 0 10" />
      </Icon>
    ),
    title: "হিউম্যান ট্রান্সফার",
    desc: "কাস্টমার মানুষ চাইলে কলটি আপনার সাপোর্ট নম্বরে চলে যায়।",
  },
  {
    icon: (
      <Icon>
        <path d="M3 17l6-6 4 4 8-8" />
        <path d="M21 13V7h-6" />
      </Icon>
    ),
    title: "RTO কমান",
    desc: "ভুয়া অর্ডার আগে থেকেই বাদ দিন — কুরিয়ার খরচ বাঁচান।",
  },
  {
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v10M9.5 9.5h5M9.5 14.5h5" />
      </Icon>
    ),
    title: "সাশ্রয়ী প্ল্যান",
    desc: "কল অনুযায়ী সীমা, বিকাশে পেমেন্ট — লুকানো খরচ নেই।",
  },
];

const STEPS: { title: string; desc: string }[] = [
  { title: "অর্ডার যোগ করুন", desc: "ড্যাশবোর্ডে কাস্টমারের নাম, ফোন আর পণ্য লিখুন — ব্যস।" },
  { title: "এআই কল করে", desc: "BanglaBot কাস্টমারকে ফোন করে বাংলায় অর্ডারের বিবরণ শুনিয়ে নিশ্চিত হতে বলে।" },
  {
    title: "ফলাফল সাথে সাথে",
    desc: "নিশ্চিত, বাতিল বা রিভিউ দরকার — স্ট্যাটাস, রেকর্ডিং ও ট্রান্সক্রিপ্টসহ ড্যাশবোর্ডে আপডেট।",
  },
];

const FAQS: { q: string; a: string }[] = [
  {
    q: "কল কি সত্যিই বাংলায় হয়?",
    a: "হ্যাঁ — এজেন্ট সম্পূর্ণ বাংলায় কথা বলে, কাস্টমারের উত্তরও বাংলাতেই বোঝে।",
  },
  {
    q: "পেমেন্ট কীভাবে করব?",
    a: "প্ল্যান নিলে ইনভয়েস তৈরি হয়; বিকাশে পেমেন্ট করে সাপোর্টে জানালেই অ্যাডমিন নিশ্চিত করে দেন।",
  },
  { q: "ট্রায়ালে কী কী থাকছে?", a: "১৪ দিন, ২০টি কল — সব ফিচারসহ। কার্ড লাগে না।" },
  {
    q: "নম্বর কোথা থেকে আসে?",
    a: "কলগুলো আমাদের প্ল্যাটফর্ম নম্বর থেকে যায়; কাস্টমার মানুষ চাইলে আপনার সাপোর্ট নম্বরে ট্রান্সফার হয়।",
  },
];

export default function Landing() {
  const { t, fmtMoney, fmtNum } = useLang();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);

  useEffect(() => {
    api<Plan[]>("/api/public/plans").then(setPlans).catch(() => {});
    api<PublicPlatform>("/api/public/platform").then(setPlatform).catch(() => {});
  }, []);

  const appHome = auth.role === "admin" ? "/admin" : "/dashboard";
  const paidPopularKey = plans.filter((p) => p.trial_days === 0)[0]?.key;

  return (
    <div className="landing">
      <header className="landing-nav">
        <span className="brand">📞 {platform?.platform_name || "BanglaBot"}</span>
        <span className="spacer" />
        <LangToggle />
        {auth.token ? (
          <Link className="btn" to={appHome}>
            {t("ড্যাশবোর্ড")}
          </Link>
        ) : (
          <>
            <Link className="btn secondary" to="/login">
              {t("লগইন")}
            </Link>
            <Link className="btn" to="/signup">
              {t("ফ্রি শুরু করুন")}
            </Link>
          </>
        )}
      </header>

      <section className="landing-hero">
        <div>
          <span className="hero-badge">{t("বাংলাদেশের ই-কমার্সের জন্য")}</span>
          <h1 className="hero-title">{t("অর্ডার কনফার্মেশন কল এখন সম্পূর্ণ স্বয়ংক্রিয়")}</h1>
          <p className="hero-sub">
            {t(
              "অর্ডার তুলুন — বাকিটা BanglaBot-এর। আমাদের এআই এজেন্ট কাস্টমারকে ফোন করে বাংলায় কথা বলে অর্ডার নিশ্চিত বা বাতিল করে, আর ফলাফল সাথে সাথে আপনার ড্যাশবোর্ডে চলে আসে।"
            )}
          </p>
          <div className="hero-ctas">
            <Link className="btn big" to="/signup">
              {t("১৪ দিন ফ্রি শুরু করুন")}
            </Link>
            <a className="btn secondary big" href="#how">
              {t("কীভাবে কাজ করে দেখুন")}
            </a>
          </div>
          <p className="hero-note">{t("কোনো কার্ড লাগবে না — সাইন আপ করেই শুরু")}</p>
        </div>
        <div className="hero-art">
          <HeroArt />
        </div>
      </section>

      <section className="landing-stats">
        {["১০০% বাংলায় কথোপকথন", "২৪/৭ কল করতে প্রস্তুত", "রিয়েল-টাইম ফলাফল"].map((s) => (
          <div className="stat-pill" key={s}>
            ✓ {t(s)}
          </div>
        ))}
      </section>

      <section className="l-section" id="how">
        <h2 className="l-section-title">{t("যেভাবে কাজ করে")}</h2>
        <div className="steps-grid">
          {STEPS.map((step, i) => (
            <div className="card step-card" key={step.title}>
              <span className="step-num">{fmtNum(i + 1)}</span>
              <h3>{t(step.title)}</h3>
              <p className="muted">{t(step.desc)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="l-section">
        <h2 className="l-section-title">{t("যা যা পাচ্ছেন")}</h2>
        <div className="features-grid">
          {FEATURES.map((f) => (
            <div className="card feature-card" key={f.title}>
              <span className="f-icon">{f.icon}</span>
              <h3>{t(f.title)}</h3>
              <p className="muted">{t(f.desc)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="l-section" id="pricing">
        <h2 className="l-section-title">{t("সহজ মূল্য")}</h2>
        <p className="l-section-sub">{t("যেকোনো সময় প্ল্যান বদলান — বিকাশে পেমেন্ট")}</p>
        <div className="plan-grid" style={{ marginTop: 22 }}>
          {plans.map((plan) => (
            <div
              className={`card plan-card${plan.key === paidPopularKey ? " current" : ""}`}
              key={plan.id}
            >
              {plan.key === paidPopularKey && <span className="badge active">{t("জনপ্রিয়")}</span>}
              <h3>{t(plan.name_bn)}</h3>
              <p className="price">
                {Number(plan.price_monthly) > 0 ? fmtMoney(plan.price_monthly) : t("ফ্রি")}
                {Number(plan.price_monthly) > 0 && (
                  <span className="muted" style={{ fontSize: 14, fontWeight: 400 }}>
                    {t("/মাস")}
                  </span>
                )}
              </p>
              <p className="muted" style={{ marginBottom: 10 }}>
                {t("মাসে {n}টি কল", { n: fmtNum(plan.max_calls_per_month) })}
              </p>
              <ul className="plan-features">
                {plan.features.map((f) => (
                  <li key={f}>✓ {t(f)}</li>
                ))}
              </ul>
              <Link className="btn" style={{ marginTop: 12, textAlign: "center" }} to="/signup">
                {t("শুরু করুন")}
              </Link>
            </div>
          ))}
        </div>
      </section>

      <section className="l-section">
        <h2 className="l-section-title">{t("সাধারণ প্রশ্ন")}</h2>
        <div className="faq-list">
          {FAQS.map((f) => (
            <details className="card faq-item" key={f.q}>
              <summary>{t(f.q)}</summary>
              <p className="muted">{t(f.a)}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="cta-band">
        <h2>{t("আজই শুরু করুন — প্রথম ১৪ দিন ফ্রি")}</h2>
        <Link className="btn big cta-invert" to="/signup">
          {t("ফ্রি অ্যাকাউন্ট খুলুন")}
        </Link>
        <p style={{ marginTop: 10 }}>
          <Link to="/login" style={{ color: "#e6f4f2", textDecoration: "underline" }}>
            {t("অ্যাকাউন্ট আছে?")} {t("লগইন")}
          </Link>
        </p>
      </section>

      <footer className="landing-footer">
        <span className="brand">📞 {platform?.platform_name || "BanglaBot"}</span>
        <span className="spacer" />
        {platform?.support_email && (
          <span className="muted">
            {t("ইমেইল")}: {platform.support_email}
          </span>
        )}
        {platform?.support_phone && (
          <span className="muted">
            {t("ফোন")}: {platform.support_phone}
          </span>
        )}
        <span className="muted">© {new Date().getFullYear()} BanglaBot</span>
      </footer>
    </div>
  );
}
