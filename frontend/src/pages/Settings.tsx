import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { FlowPreview, Merchant, VoiceTier } from "../api/types";
import { useLang } from "../i18n";

const GREETING_MAX = 200;

/** Call-length choices (seconds); 0 = platform default. */
const DURATION_CHOICES = [0, 60, 120, 180, 240, 300, 360, 480, 600];

/** Caller-silence hang-up choices (seconds). */
const SILENCE_CHOICES = [5, 10, 15, 20, 30];

const NOISE_MODES = [
  { key: "normal", label: "সাধারণ পরিবেশ" },
  { key: "noisy", label: "বেশি আওয়াজের পরিবেশ (কড়া ফিল্টার)" },
];

const BARGE_IN_MODES = [
  { key: "protected", label: "সুরক্ষিত — কয়েক শব্দ শুনে তবেই থামবে" },
  { key: "normal", label: "সাথে সাথে থামবে" },
  { key: "off", label: "থামবে না — কথা শেষ করে শুনবে" },
];

const SECTIONS = [
  { key: "profile", icon: "🏪", label: "প্রোফাইল", hint: "দোকানের নাম ও যোগাযোগের তথ্য" },
  { key: "agent", icon: "🎙", label: "এজেন্ট ও ভয়েস", hint: "এজেন্ট কীভাবে কথা বলবে ও কোন কণ্ঠে" },
  { key: "flow", icon: "🔀", label: "কল ফ্লো", hint: "সার্ভিস অনুযায়ী কলের ধাপ ও প্রশ্ন" },
  { key: "security", icon: "🔒", label: "নিরাপত্তা", hint: "লগইন পাসওয়ার্ড বদলান" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

export default function Settings() {
  const { t, fmtNum } = useLang();
  const [section, setSection] = useState<SectionKey>("profile");
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [form, setForm] = useState({ owner_name: "", phone: "", support_phone: "", email: "" });
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [agentForm, setAgentForm] = useState({
    custom_greeting: "",
    max_call_seconds: 0,
    voice_tier: "very_basic",
    noise_mode: "normal",
    barge_in_mode: "protected",
    silence_hangup_secs: 10,
  });
  const [tiers, setTiers] = useState<VoiceTier[]>([]);
  const [playingTier, setPlayingTier] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  // Tiers whose sample clip 404s — remembered so selecting them again stays quiet.
  const [noSample, setNoSample] = useState<Record<string, boolean>>({});
  const sampleAudio = useRef<HTMLAudioElement | null>(null);

  function stopSample() {
    sampleAudio.current?.pause();
    sampleAudio.current = null;
    setPlayingTier(null);
    setProgress(0);
  }

  // Stop any playing sample when leaving the page.
  useEffect(() => stopSample, []);

  /** Play a tier's preview clip. Silent no-op for tiers we know have no clip. */
  function playSample(tierKey: string, force = false) {
    if (noSample[tierKey] && !force) return;
    stopSample();
    // Sample clips live in frontend/public/voice-samples/<tier-key>.mp3.
    const audio = new Audio(`/voice-samples/${tierKey}.mp3`);
    sampleAudio.current = audio;
    audio.ontimeupdate = () => {
      if (audio.duration) setProgress(audio.currentTime / audio.duration);
    };
    audio.onended = () => stopSample();
    audio.onerror = () => {
      setNoSample((m) => ({ ...m, [tierKey]: true }));
      stopSample();
    };
    audio
      .play()
      .then(() => {
        setPlayingTier(tierKey);
        setNoSample((m) => (m[tierKey] ? { ...m, [tierKey]: false } : m));
      })
      .catch(() => {
        setNoSample((m) => ({ ...m, [tierKey]: true }));
        stopSample();
      });
  }

  function toggleSample(tierKey: string) {
    if (playingTier === tierKey) stopSample();
    else playSample(tierKey, true);
  }

  function pickTier(tierKey: string) {
    setAgentForm((f) => ({ ...f, voice_tier: tierKey }));
    playSample(tierKey);
  }

  const [agentMsg, setAgentMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [flow, setFlow] = useState<FlowPreview | null>(null);
  const [flowForm, setFlowForm] = useState<Record<string, boolean>>({});
  const [flowMsg, setFlowMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [flowBusy, setFlowBusy] = useState(false);
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
          noise_mode: m.noise_mode || "normal",
          barge_in_mode: m.barge_in_mode || "protected",
          silence_hangup_secs: m.silence_hangup_secs || 10,
        });
      })
      .catch((e) => setProfileMsg({ ok: false, text: e.message }));
    api<VoiceTier[]>("/api/public/voice-tiers").then(setTiers).catch(() => {});
    loadFlow();
  }, []);

  function loadFlow() {
    api<FlowPreview>("/api/auth/flow-preview")
      .then((f) => {
        setFlow(f);
        setFlowForm(Object.fromEntries(f.settings.map((s) => [s.key, s.value])));
      })
      .catch(() => {});
  }

  async function saveFlow(e: FormEvent) {
    e.preventDefault();
    setFlowMsg(null);
    setFlowBusy(true);
    try {
      await api<Merchant>("/api/auth/me", {
        method: "PATCH",
        body: { flow_settings: flowForm },
      });
      loadFlow();
      setFlowMsg({ ok: true, text: "সংরক্ষণ হয়েছে" });
    } catch (err) {
      setFlowMsg({ ok: false, text: (err as Error).message });
    } finally {
      setFlowBusy(false);
    }
  }

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
        noise_mode: m.noise_mode || "normal",
        barge_in_mode: m.barge_in_mode || "protected",
        silence_hangup_secs: m.silence_hangup_secs || 10,
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

  const selectedTier = tiers.find((tier) => tier.key === agentForm.voice_tier);

  function renderTierCard(tier: VoiceTier) {
    const selected = agentForm.voice_tier === tier.key;
    const playing = playingTier === tier.key;
    return (
      <div
        key={tier.key}
        role="radio"
        aria-checked={selected}
        tabIndex={0}
        className={`tier-card${selected ? " selected" : ""}${playing ? " playing" : ""}`}
        onClick={() => pickTier(tier.key)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            pickTier(tier.key);
          }
        }}
      >
        <span className="tier-name">
          {t(tier.name_bn)}
          {selected && <span className="tier-check">✓</span>}
        </span>
        <span className="muted tier-desc">{t(tier.description_bn)}</span>
        <span className="tier-tags">
          {tier.gender && (
            <span className="tier-mode">{t(tier.gender === "female" ? "মহিলা" : "পুরুষ")}</span>
          )}
          {tier.accent_bn && <span className="tier-mode">{t(tier.accent_bn)}</span>}
          {tier.mode === "static" && (
            <span className="tier-mode">🔢 {t("কীপ্যাড — বাটন চাপ")}</span>
          )}
        </span>
        <span className="tier-foot">
          <span className="tier-price">
            {tier.multiplier === 1
              ? t("সাধারণ মিনিট খরচ")
              : t("মিনিট খরচ ×{n}", { n: fmtNum(tier.multiplier) })}
          </span>
          <button
            type="button"
            className="tier-play"
            title={t(playing ? "নমুনা বন্ধ করুন" : "এই ভয়েসের নমুনা শুনুন")}
            aria-label={t(playing ? "নমুনা বন্ধ করুন" : "এই ভয়েসের নমুনা শুনুন")}
            onClick={(e) => {
              e.stopPropagation();
              toggleSample(tier.key);
            }}
          >
            {playing ? "⏸" : "▶"}
          </button>
        </span>
        {playing ? (
          <span className="tier-progress" aria-hidden="true">
            <i style={{ width: `${Math.round(progress * 100)}%` }} />
          </span>
        ) : noSample[tier.key] ? (
          <span className="tier-nosample">🔇 {t("এই ভয়েসের স্যাম্পল এখনো যোগ করা হয়নি")}</span>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <div className="settings-head">
        <h1 className="page-title" style={{ marginBottom: 2 }}>
          {t("সেটিংস")}
        </h1>
        <div className="muted" style={{ fontSize: 13.5 }}>
          {merchant.business_name}
        </div>
      </div>

      <div className="settings-layout">
        <nav className="settings-nav" aria-label={t("সেটিংস")}>
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              className={`settings-nav-item${section === s.key ? " active" : ""}`}
              aria-current={section === s.key}
              onClick={() => setSection(s.key)}
            >
              <span className="settings-nav-icon" aria-hidden="true">
                {s.icon}
              </span>
              <span>
                <span className="settings-nav-label">{t(s.label)}</span>
                <span className="settings-nav-hint">{t(s.hint)}</span>
              </span>
            </button>
          ))}
        </nav>

        <div className="settings-main">
          {section === "profile" && (
            <form className="card form" onSubmit={saveProfile}>
              <div className="card-head">
                <h2>{t("প্রোফাইল")}</h2>
                <p className="muted">{t("দোকানের নাম ও যোগাযোগের তথ্য")}</p>
              </div>
              <div className="field-grid">
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
              </div>
              <div className="form-actions">
                {profileMsg && (
                  <span className={profileMsg.ok ? "save-ok" : "error"}>{t(profileMsg.text)}</span>
                )}
                <button className="btn" disabled={profileBusy}>
                  {profileBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
                </button>
              </div>
            </form>
          )}

          {section === "agent" && (
            <form className="card form" onSubmit={saveAgent}>
              <div className="card-head">
                <h2>{t("এজেন্ট সেটিংস")}</h2>
                <p className="muted">{t("এজেন্ট কীভাবে কথা বলবে ও কোন কণ্ঠে")}</p>
              </div>

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
                <div className="field-foot">
                  <span className="muted">
                    {t("খালি রাখলে এজেন্ট নিজের মতো সালাম ও পরিচয় দিয়ে শুরু করবে।")}
                  </span>
                  <span className="muted">
                    {t("{used}/{max} অক্ষর", {
                      used: fmtNum(agentForm.custom_greeting.length),
                      max: fmtNum(GREETING_MAX),
                    })}
                  </span>
                </div>
              </div>

              <div className="form-row voice-picker">
                <label>
                  {t("ভয়েস")}
                  {selectedTier && (
                    <span className="voice-current">
                      {t("নির্বাচিত")}: {t(selectedTier.name_bn)}
                    </span>
                  )}
                </label>
                <div className="muted hint">
                  {t("কার্ডে ক্লিক করলেই কণ্ঠের নমুনা বাজবে — শুনে তারপর বাছুন।")}
                </div>
                {/* One flat list — every voice option (named speakers, keypad and
                    the AI quality ranks) lives under the same heading. */}
                <div className="tier-group">
                  <div className="tier-section">{t("বাংলা কণ্ঠ")}</div>
                  <div className="tier-grid">{tiers.map(renderTierCard)}</div>
                </div>
                <div className="muted hint">
                  {t("ভালো ভয়েস বাছলে প্রতি মিনিট কথা প্ল্যানের মিনিট সীমা থেকে বেশি কাটবে — যেমন ×২ মানে ১ মিনিট কথায় ২ মিনিট খরচ।")}
                </div>
              </div>

              <div className="field-grid">
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
                  <div className="muted hint">
                    {t("সময় শেষ হলে কলটি স্বয়ংক্রিয়ভাবে কেটে যাবে — বিল ও খরচ নিয়ন্ত্রণে রাখতে সাহায্য করে।")}
                  </div>
                </div>

                <div className="form-row">
                  <label>{t("কাস্টমার চুপ থাকলে কল কাটা")}</label>
                  <select
                    value={agentForm.silence_hangup_secs}
                    onChange={(e) =>
                      setAgentForm((f) => ({ ...f, silence_hangup_secs: Number(e.target.value) }))
                    }
                  >
                    {SILENCE_CHOICES.map((secs) => (
                      <option key={secs} value={secs}>
                        {t("{n} সেকেন্ড", { n: fmtNum(secs) })}
                      </option>
                    ))}
                  </select>
                  <div className="muted hint">
                    {t("এজেন্টের কথার পরে এতক্ষণ কাস্টমার কিছু না বললে কলটি কেটে যাবে — অর্ডারটি আবার কল করা যাবে।")}
                  </div>
                </div>

                <div className="form-row">
                  <label>{t("পরিবেশের আওয়াজ ফিল্টার")}</label>
                  <select
                    value={agentForm.noise_mode}
                    onChange={(e) => setAgentForm((f) => ({ ...f, noise_mode: e.target.value }))}
                  >
                    {NOISE_MODES.map((m) => (
                      <option key={m.key} value={m.key}>
                        {t(m.label)}
                      </option>
                    ))}
                  </select>
                  <div className="muted hint">
                    {t("কড়া ফিল্টারে রাস্তা/দোকানের আওয়াজ কাস্টমারের কথা হিসেবে ধরা হবে না।")}
                  </div>
                </div>

                <div className="form-row">
                  <label>{t("কথার মাঝে থামানো (বার্জ-ইন)")}</label>
                  <select
                    value={agentForm.barge_in_mode}
                    onChange={(e) =>
                      setAgentForm((f) => ({ ...f, barge_in_mode: e.target.value }))
                    }
                  >
                    {BARGE_IN_MODES.map((m) => (
                      <option key={m.key} value={m.key}>
                        {t(m.label)}
                      </option>
                    ))}
                  </select>
                  <div className="muted hint">
                    {t("কাস্টমার কথা বললে এজেন্ট কখন থামবে — সুরক্ষিত মোডে হালকা শব্দ বা খুকখুকিতে এজেন্ট থামবে না।")}
                  </div>
                </div>
              </div>

              <div className="form-actions">
                {agentMsg && (
                  <span className={agentMsg.ok ? "save-ok" : "error"}>{t(agentMsg.text)}</span>
                )}
                <button className="btn" disabled={agentBusy}>
                  {agentBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
                </button>
              </div>
            </form>
          )}

          {section === "flow" && (
            <form className="card form" onSubmit={saveFlow}>
              <div className="card-head">
                <h2>{t("কল ফ্লো")}</h2>
                <p className="muted">
                  {t("এজেন্ট ধাপে ধাপে প্রশ্ন করে — কাস্টমার আগে থেকে কিছু বলে দিলে সেই ধাপ নিজে থেকেই বাদ যায়।")}
                </p>
              </div>
              {!flow ? (
                <p className="muted">{t("লোড হচ্ছে...")}</p>
              ) : (
                <>
                  <div className="form-row">
                    <label>{t("আপনার সার্ভিস")}</label>
                    <div>
                      <span className="badge active">
                        {flow.service_icon} {t(flow.service_name_bn)}
                      </span>{" "}
                      <span className="muted" style={{ fontSize: 13.5 }}>
                        {t(flow.description_bn)}
                      </span>
                    </div>
                    <div className="muted hint">
                      {t("সার্ভিস টাইপ বদলাতে হলে প্ল্যাটফর্ম অ্যাডমিনের সাথে যোগাযোগ করুন।")}
                    </div>
                  </div>

                  {flow.settings.length > 0 && (
                    <div className="form-row">
                      <label>{t("ঐচ্ছিক ধাপ")}</label>
                      <div style={{ display: "grid", gap: 8 }}>
                        {flow.settings.map((s) => (
                          <label
                            key={s.key}
                            style={{ display: "flex", gap: 8, alignItems: "start", fontWeight: 400 }}
                          >
                            <input
                              type="checkbox"
                              checked={flowForm[s.key] ?? s.value}
                              onChange={(e) =>
                                setFlowForm((f) => ({ ...f, [s.key]: e.target.checked }))
                              }
                              style={{ marginTop: 3 }}
                            />
                            <span>
                              {t(s.label_bn)}
                              <span className="muted" style={{ display: "block", fontSize: 13 }}>
                                {t(s.hint_bn)}
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="form-row">
                    <label>{t("কলের ধাপগুলো (বর্তমান সেটিং অনুযায়ী)")}</label>
                    <ol style={{ paddingInlineStart: 20, display: "grid", gap: 6, margin: 0 }}>
                      {flow.steps_bn.map((step, i) => (
                        <li key={i}>{t(step)}</li>
                      ))}
                    </ol>
                    <div className="muted hint">
                      {t("সেভ করার পরে তালিকাটি নতুন সেটিং অনুযায়ী আপডেট হবে।")}
                    </div>
                  </div>

                  <div className="form-actions">
                    {flowMsg && (
                      <span className={flowMsg.ok ? "save-ok" : "error"}>{t(flowMsg.text)}</span>
                    )}
                    <button className="btn" disabled={flowBusy}>
                      {flowBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
                    </button>
                  </div>
                </>
              )}
            </form>
          )}

          {section === "security" && (
            <form className="card form" onSubmit={savePassword}>
              <div className="card-head">
                <h2>{t("পাসওয়ার্ড পরিবর্তন")}</h2>
                <p className="muted">{t("লগইন পাসওয়ার্ড বদলান")}</p>
              </div>
              <div className="field-grid">
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
              </div>
              <div className="form-actions">
                {passMsg && (
                  <span className={passMsg.ok ? "save-ok" : "error"}>{t(passMsg.text)}</span>
                )}
                <button className="btn" disabled={passBusy}>
                  {passBusy ? t("সংরক্ষণ হচ্ছে...") : t("পাসওয়ার্ড বদলান")}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </>
  );
}
