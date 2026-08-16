import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { Merchant, VoiceTier } from "../api/types";
import { useLang } from "../i18n";

const GREETING_MAX = 200;

/** Call-length choices (seconds); 0 = platform default. */
const DURATION_CHOICES = [0, 60, 120, 180, 240, 300, 360, 480, 600];

export default function Settings() {
  const { t, fmtNum } = useLang();
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [form, setForm] = useState({ owner_name: "", phone: "", support_phone: "", email: "" });
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [agentForm, setAgentForm] = useState({
    custom_greeting: "",
    max_call_seconds: 0,
    voice_tier: "very_basic",
  });
  const [tiers, setTiers] = useState<VoiceTier[]>([]);
  const [playingTier, setPlayingTier] = useState<string | null>(null);
  const [sampleMsg, setSampleMsg] = useState("");
  const sampleAudio = useRef<HTMLAudioElement | null>(null);

  // Stop any playing sample when leaving the page.
  useEffect(() => () => sampleAudio.current?.pause(), []);

  function toggleSample(tierKey: string) {
    if (playingTier === tierKey) {
      sampleAudio.current?.pause();
      setPlayingTier(null);
      return;
    }
    sampleAudio.current?.pause();
    setSampleMsg("");
    // Sample clips live in frontend/public/voice-samples/<tier-key>.mp3.
    const audio = new Audio(`/voice-samples/${tierKey}.mp3`);
    sampleAudio.current = audio;
    audio.onended = () => setPlayingTier(null);
    audio.onerror = () => {
      setPlayingTier(null);
      setSampleMsg("এই ভয়েসের স্যাম্পল এখনো যোগ করা হয়নি");
    };
    audio
      .play()
      .then(() => setPlayingTier(tierKey))
      .catch(() => {
        setPlayingTier(null);
        setSampleMsg("এই ভয়েসের স্যাম্পল এখনো যোগ করা হয়নি");
      });
  }
  const [agentMsg, setAgentMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passMsg, setPassMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [passBusy, setPassBusy] = useState(false);

  useEffect(() => {
    api<Merchant>("/api/auth/me")
      .then((m) => {
        setMerchant(m);
        setForm({
          owner_name: m.owner_name,
          phone: m.phone,
          support_phone: m.support_phone,
          email: m.email,
        });
        setAgentForm({
          custom_greeting: m.custom_greeting,
          max_call_seconds: m.max_call_seconds,
          voice_tier: m.voice_tier || "very_basic",
        });
      })
      .catch((e) => setProfileMsg({ ok: false, text: e.message }));
    api<VoiceTier[]>("/api/public/voice-tiers").then(setTiers).catch(() => {});
  }, []);

  const set = (key: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileMsg(null);
    setProfileBusy(true);
    try {
      const m = await api<Merchant>("/api/auth/me", { method: "PATCH", body: form });
      setMerchant(m);
      setProfileMsg({ ok: true, text: "সংরক্ষণ হয়েছে" });
    } catch (err) {
      setProfileMsg({ ok: false, text: (err as Error).message });
    } finally {
      setProfileBusy(false);
    }
  }

  async function saveAgent(e: FormEvent) {
    e.preventDefault();
    setAgentMsg(null);
    setAgentBusy(true);
    try {
      const m = await api<Merchant>("/api/auth/me", { method: "PATCH", body: agentForm });
      setMerchant(m);
      setAgentForm({
        custom_greeting: m.custom_greeting,
        max_call_seconds: m.max_call_seconds,
        voice_tier: m.voice_tier || "very_basic",
      });
      setAgentMsg({ ok: true, text: "সংরক্ষণ হয়েছে" });
    } catch (err) {
      setAgentMsg({ ok: false, text: (err as Error).message });
    } finally {
      setAgentBusy(false);
    }
  }

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    setPassMsg(null);
    setPassBusy(true);
    try {
      await api<Merchant>("/api/auth/me", {
        method: "PATCH",
        body: { current_password: currentPassword, password: newPassword },
      });
      setCurrentPassword("");
      setNewPassword("");
      setPassMsg({ ok: true, text: "পাসওয়ার্ড বদলানো হয়েছে" });
    } catch (err) {
      setPassMsg({ ok: false, text: (err as Error).message });
    } finally {
      setPassBusy(false);
    }
  }

  if (!merchant) return <p className="muted">{t(profileMsg?.text || "লোড হচ্ছে...")}</p>;

  return (
    <>
      <h1 className="page-title">{t("সেটিংস")}</h1>
      <form className="card form" style={{ marginBottom: 16 }} onSubmit={saveProfile}>
        <h2 className="page-title" style={{ fontSize: 17, marginBottom: 0 }}>
          {t("প্রোফাইল")} — {merchant.business_name}
        </h2>
        <div className="form-row">
          <label>{t("মালিকের নাম")}</label>
          <input value={form.owner_name} onChange={set("owner_name")} />
        </div>
        <div className="form-row">
          <label>{t("ফোন নম্বর")}</label>
          <input value={form.phone} onChange={set("phone")} />
        </div>
        <div className="form-row">
          <label>{t("সাপোর্ট ফোন (কলে কাস্টমারকে বলা হবে)")}</label>
          <input value={form.support_phone} onChange={set("support_phone")} />
        </div>
        <div className="form-row">
          <label>{t("ইমেইল")}</label>
          <input type="email" value={form.email} onChange={set("email")} />
        </div>
        {profileMsg && (
          <div className={profileMsg.ok ? "muted" : "error"}>{t(profileMsg.text)}</div>
        )}
        <div>
          <button className="btn" disabled={profileBusy}>
            {profileBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
          </button>
        </div>
      </form>

      <form className="card form" style={{ marginBottom: 16 }} onSubmit={saveAgent}>
        <h2 className="page-title" style={{ fontSize: 17, marginBottom: 0 }}>
          {t("এজেন্ট সেটিংস")}
        </h2>
        <div className="form-row">
          <label>{t("কলের শুরুর কথা (এজেন্ট হুবহু এই বাক্য দিয়ে শুরু করবে)")}</label>
          <textarea
            rows={3}
            maxLength={GREETING_MAX}
            value={agentForm.custom_greeting}
            onChange={(e) =>
              setAgentForm((f) => ({ ...f, custom_greeting: e.target.value }))
            }
            placeholder={t("যেমন: আসসালামু আলাইকুম, আমি {shop} থেকে বলছি।", {
              shop: merchant.business_name,
            })}
          />
          <div
            className="muted"
            style={{ fontSize: 12.5, textAlign: "right" }}
          >
            {t("{used}/{max} অক্ষর", {
              used: fmtNum(agentForm.custom_greeting.length),
              max: fmtNum(GREETING_MAX),
            })}
          </div>
          <div className="muted" style={{ fontSize: 12.5 }}>
            {t("খালি রাখলে এজেন্ট নিজের মতো সালাম ও পরিচয় দিয়ে শুরু করবে।")}
          </div>
        </div>
        <div className="form-row">
          <label>{t("ভয়েস কোয়ালিটি")}</label>
          <div className="tier-grid">
            {tiers.map((tier) => (
              <div
                key={tier.key}
                role="radio"
                aria-checked={agentForm.voice_tier === tier.key}
                tabIndex={0}
                className={`tier-card ${agentForm.voice_tier === tier.key ? "selected" : ""}`}
                onClick={() => setAgentForm((f) => ({ ...f, voice_tier: tier.key }))}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setAgentForm((f) => ({ ...f, voice_tier: tier.key }));
                  }
                }}
              >
                <span className="tier-name">
                  {t(tier.name_bn)}
                  {agentForm.voice_tier === tier.key && <span className="tier-check">✓</span>}
                </span>
                <span className="muted tier-desc">{t(tier.description_bn)}</span>
                {tier.mode === "static" && (
                  <span className="tier-mode">🔢 {t("কীপ্যাড — বাটন চাপ")}</span>
                )}
                <span className="tier-foot">
                  <span className="tier-price">
                    {tier.multiplier === 1
                      ? t("সাধারণ মিনিট খরচ")
                      : t("মিনিট খরচ ×{n}", { n: fmtNum(tier.multiplier) })}
                  </span>
                  <button
                    type="button"
                    className="tier-play"
                    title={t("এই ভয়েসের নমুনা শুনুন")}
                    aria-label={t("এই ভয়েসের নমুনা শুনুন")}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleSample(tier.key);
                    }}
                  >
                    {playingTier === tier.key ? "⏸" : "▶"}
                  </button>
                </span>
              </div>
            ))}
          </div>
          {sampleMsg && (
            <div className="muted" style={{ fontSize: 12.5 }}>
              🔇 {t(sampleMsg)}
            </div>
          )}
          <div className="muted" style={{ fontSize: 12.5 }}>
            {t("ভালো ভয়েস বাছলে প্রতি মিনিট কথা প্ল্যানের মিনিট সীমা থেকে বেশি কাটবে — যেমন ×২ মানে ১ মিনিট কথায় ২ মিনিট খরচ।")}
          </div>
        </div>
        <div className="form-row">
          <label>{t("এক কলের সর্বোচ্চ সময়")}</label>
          <select
            value={agentForm.max_call_seconds}
            onChange={(e) =>
              setAgentForm((f) => ({ ...f, max_call_seconds: Number(e.target.value) }))
            }
          >
            {DURATION_CHOICES.map((secs) => (
              <option key={secs} value={secs}>
                {secs === 0
                  ? t("ডিফল্ট (৪ মিনিট)")
                  : t("{n} মিনিট", { n: fmtNum(secs / 60) })}
              </option>
            ))}
          </select>
          <div className="muted" style={{ fontSize: 12.5 }}>
            {t("সময় শেষ হলে কলটি স্বয়ংক্রিয়ভাবে কেটে যাবে — বিল ও খরচ নিয়ন্ত্রণে রাখতে সাহায্য করে।")}
          </div>
        </div>
        {agentMsg && <div className={agentMsg.ok ? "muted" : "error"}>{t(agentMsg.text)}</div>}
        <div>
          <button className="btn" disabled={agentBusy}>
            {agentBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
          </button>
        </div>
      </form>

      <form className="card form" onSubmit={savePassword}>
        <h2 className="page-title" style={{ fontSize: 17, marginBottom: 0 }}>
          {t("পাসওয়ার্ড পরিবর্তন")}
        </h2>
        <div className="form-row">
          <label>{t("বর্তমান পাসওয়ার্ড")}</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
        </div>
        <div className="form-row">
          <label>{t("নতুন পাসওয়ার্ড (কমপক্ষে ৬ অক্ষর)")}</label>
          <input
            type="password"
            minLength={6}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </div>
        {passMsg && <div className={passMsg.ok ? "muted" : "error"}>{t(passMsg.text)}</div>}
        <div>
          <button className="btn" disabled={passBusy}>
            {passBusy ? t("সংরক্ষণ হচ্ছে...") : t("পাসওয়ার্ড বদলান")}
          </button>
        </div>
      </form>
    </>
  );
}
