import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";
import { LangToggle, useLang } from "../i18n";
import { clearServiceCache } from "../service";

export default function Login() {
  const { t } = useLang();
  const [tab, setTab] = useState<"merchant" | "admin">("merchant");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const path = tab === "admin" ? "/api/auth/admin/login" : "/api/auth/login";
      const res = await api<{ access_token: string; role: string; name: string }>(path, {
        method: "POST",
        body: { username, password },
      });
      auth.save(res.access_token, res.role, res.name);
      clearServiceCache();
      navigate(res.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Link to="/" className="muted" style={{ fontSize: 13.5 }}>
            ← {t("হোম")}
          </Link>
          <LangToggle />
        </div>
        <h1>📞 BanglaBot</h1>
        <p className="muted" style={{ textAlign: "center" }}>
          {t("বাংলায় অর্ডার কনফার্মেশন কল — স্বয়ংক্রিয়ভাবে")}
        </p>
        <div className="tabs">
          <button type="button" className={tab === "merchant" ? "active" : ""} onClick={() => setTab("merchant")}>
            {t("মার্চেন্ট")}
          </button>
          <button type="button" className={tab === "admin" ? "active" : ""} onClick={() => setTab("admin")}>
            {t("অ্যাডমিন")}
          </button>
        </div>
        <div className="form-row">
          <label>{t("ইউজারনেম")}</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="form-row">
          <label>{t("পাসওয়ার্ড")}</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && <div className="error">{t(error)}</div>}
        <button className="btn" disabled={busy}>
          {busy ? t("লগইন হচ্ছে...") : t("লগইন")}
        </button>
        <p className="muted" style={{ textAlign: "center" }}>
          <Link to="/signup">{t("নতুন? বিনামূল্যে সাইন আপ করুন")}</Link>
        </p>
      </form>
    </div>
  );
}
