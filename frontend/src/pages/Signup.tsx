import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";
import { Plan } from "../api/types";
import { LangToggle, useLang } from "../i18n";

interface PublicPlatform {
  platform_name: string;
  support_email: string;
  support_phone: string;
  bkash_number: string;
  signup_enabled: boolean;
}

export default function Signup() {
  const { t, fmtMoney } = useLang();
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState({
    business_name: "",
    owner_name: "",
    username: "",
    password: "",
    phone: "",
    email: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api<PublicPlatform>("/api/public/platform").then(setPlatform).catch(() => {});
    api<Plan[]>("/api/public/plans").then(setPlans).catch(() => {});
  }, []);

  const set = (key: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api<{ access_token: string; role: string; name: string }>(
        "/api/auth/signup",
        { method: "POST", body: form }
      );
      auth.save(res.access_token, res.role, res.name);
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  if (platform && !platform.signup_enabled) {
    return (
      <div className="login-wrap">
        <div className="card login-card">
          <h1>📞 BanglaBot</h1>
          <p style={{ textAlign: "center" }}>{t("সাইন আপ বন্ধ আছে")}</p>
          <p className="muted" style={{ textAlign: "center" }}>
            {t("অ্যাকাউন্ট খুলতে সাপোর্টে যোগাযোগ করুন")}
            {platform.support_phone && <> — {t("ফোন")}: {platform.support_phone}</>}
            {platform.support_email && <> — {t("ইমেইল")}: {platform.support_email}</>}
          </p>
          <p className="muted" style={{ textAlign: "center" }}>
            <Link to="/login">← {t("লগইনে ফিরুন")}</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-wrap">
      <div className="card login-card" style={{ width: 760, maxWidth: "94vw", margin: "32px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Link to="/" className="muted" style={{ fontSize: 13.5 }}>
            ← {t("হোম")}
          </Link>
          <LangToggle />
        </div>
        <h1>📞 BanglaBot</h1>
        <p className="muted" style={{ textAlign: "center" }}>
          {t("১৪ দিন ফ্রি ট্রায়াল দিয়ে শুরু করুন — কোনো কার্ড লাগবে না")}
        </p>
        {plans.length > 0 && (
          <div className="plan-grid">
            {plans.map((plan) => (
              <div className={`plan-card ${plan.trial_days > 0 ? "current" : ""}`} key={plan.id}>
                <b>{t(plan.name_bn)}</b>
                <div className="price">
                  {fmtMoney(plan.price_monthly)}
                  <span className="muted" style={{ fontSize: 14, fontWeight: 400 }}>{t("/মাস")}</span>
                </div>
                <ul style={{ paddingInlineStart: 18, display: "grid", gap: 4, fontSize: 14 }}>
                  {plan.features.map((f, i) => (
                    <li key={i}>{t(f)}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
        <form className="form" style={{ maxWidth: "none" }} onSubmit={submit}>
          <div className="form-row">
            <label>{t("ব্যবসার নাম *")}</label>
            <input value={form.business_name} onChange={set("business_name")} required />
          </div>
          <div className="form-row">
            <label>{t("মালিকের নাম")}</label>
            <input value={form.owner_name} onChange={set("owner_name")} />
          </div>
          <div className="form-row">
            <label>{t("ইউজারনেম *")}</label>
            <input value={form.username} onChange={set("username")} required />
          </div>
          <div className="form-row">
            <label>{t("পাসওয়ার্ড * (কমপক্ষে ৬ অক্ষর)")}</label>
            <input type="password" minLength={6} value={form.password} onChange={set("password")} required />
          </div>
          <div className="form-row">
            <label>{t("ফোন নম্বর")}</label>
            <input value={form.phone} onChange={set("phone")} placeholder="01712345678" />
          </div>
          <div className="form-row">
            <label>{t("ইমেইল")}</label>
            <input type="email" value={form.email} onChange={set("email")} />
          </div>
          {error && <div className="error">{t(error)}</div>}
          <button className="btn" disabled={busy}>
            {busy ? t("অ্যাকাউন্ট খোলা হচ্ছে...") : t("ফ্রি ট্রায়াল শুরু করুন")}
          </button>
        </form>
        <p className="muted" style={{ textAlign: "center" }}>
          {t("আগে থেকেই অ্যাকাউন্ট আছে?")} <Link to="/login">{t("লগইন করুন")}</Link>
        </p>
      </div>
    </div>
  );
}
