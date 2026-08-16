import { FormEvent, useEffect, useState } from "react";
import { api } from "../../api/client";
import { Plan, PlatformSettingsData } from "../../api/types";
import { useLang } from "../../i18n";

export default function AdminSettings() {
  const { t } = useLang();
  const [settings, setSettings] = useState<PlatformSettingsData | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<PlatformSettingsData>("/api/admin/settings").then(setSettings).catch((e) => setError(e.message));
    api<Plan[]>("/api/admin/plans").then(setPlans).catch(() => {});
  }, []);

  const set = (key: keyof PlatformSettingsData) => (e: { target: { value: string } }) =>
    setSettings((s) => (s ? { ...s, [key]: e.target.value } : s));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!settings) return;
    setError("");
    setSaved(false);
    setBusy(true);
    try {
      const res = await api<PlatformSettingsData>("/api/admin/settings", {
        method: "PATCH",
        body: {
          platform_name: settings.platform_name,
          support_email: settings.support_email,
          support_phone: settings.support_phone,
          bkash_number: settings.bkash_number,
          signup_enabled: settings.signup_enabled,
          trial_plan_key: settings.trial_plan_key,
          entitlement_mode: settings.entitlement_mode,
        },
      });
      setSettings(res);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!settings) return <p className="muted">{error ? t(error) : t("লোড হচ্ছে...")}</p>;

  const trialPlans = plans.filter((p) => p.trial_days > 0);

  return (
    <>
      <h1 className="page-title">{t("প্ল্যাটফর্ম সেটিংস")}</h1>
      {error && <p className="error">{t(error)}</p>}
      <form className="card form" onSubmit={submit}>
        <div className="form-row">
          <label>{t("প্ল্যাটফর্মের নাম")}</label>
          <input value={settings.platform_name} onChange={set("platform_name")} />
        </div>
        <div className="form-row">
          <label>{t("সাপোর্ট ইমেইল")}</label>
          <input type="email" value={settings.support_email} onChange={set("support_email")} />
        </div>
        <div className="form-row">
          <label>{t("সাপোর্ট ফোন")}</label>
          <input value={settings.support_phone} onChange={set("support_phone")} />
        </div>
        <div className="form-row">
          <label>{t("বিকাশ নম্বর (মার্চেন্ট পেমেন্টের জন্য)")}</label>
          <input value={settings.bkash_number} onChange={set("bkash_number")} />
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14.5 }}>
          <input
            type="checkbox"
            checked={settings.signup_enabled}
            onChange={(e) => setSettings((s) => (s ? { ...s, signup_enabled: e.target.checked } : s))}
            style={{ width: "auto" }}
          />
          {t("নতুন সাইন আপ চালু")}
        </label>
        <div className="form-row">
          <label>{t("ট্রায়াল প্ল্যান")}</label>
          <select value={settings.trial_plan_key} onChange={set("trial_plan_key")}>
            {trialPlans.length === 0 && <option value={settings.trial_plan_key}>{settings.trial_plan_key}</option>}
            {trialPlans.map((p) => (
              <option key={p.key} value={p.key}>
                {t(p.name_bn)} ({p.key})
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>{t("এনটাইটেলমেন্ট মোড")}</label>
          <select value={settings.entitlement_mode} onChange={set("entitlement_mode")}>
            <option value="enforce">{t("কঠোর (কল আটকাবে)")}</option>
            <option value="observe">{t("পর্যবেক্ষণ (শুধু লগ)")}</option>
          </select>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button className="btn" disabled={busy}>
            {busy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
          </button>
          {saved && <span className="muted">{t("সংরক্ষিত হয়েছে ✓")}</span>}
        </div>
      </form>
    </>
  );
}
