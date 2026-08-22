import { FormEvent, Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import {
  AdminMerchant,
  Page,
  Plan,
  SERVICE_LABELS,
  ServiceTypeInfo,
  SubStatus,
  SUB_STATUS_LABELS,
  VoiceTier,
} from "../../api/types";
import EmptyState from "../../components/EmptyState";
import Pagination from "../../components/Pagination";
import { GreetingArt } from "../../components/art";
import { useLang } from "../../i18n";

const PAGE_SIZE = 15;
const EMPTY = {
  business_name: "",
  owner_name: "",
  username: "",
  password: "",
  phone: "",
  support_phone: "",
  email: "",
  service_type: "ecommerce",
};
const EMPTY_SUB = {
  plan_key: "",
  status: "",
  bonus_calls: "",
  bonus_minutes: "",
  extend_days: "",
  note: "",
};
const EMPTY_EDIT = {
  business_name: "",
  owner_name: "",
  phone: "",
  email: "",
  support_phone: "",
  custom_greeting: "",
  max_call_seconds: 0,
  voice_tier: "very_basic",
  service_type: "ecommerce",
};
const DURATION_CHOICES = [0, 60, 120, 180, 240, 300, 360, 480, 600];

export default function AdminMerchants() {
  const { t, fmtNum } = useLang();
  const [data, setData] = useState<Page<AdminMerchant> | null>(null);
  const [page, setPage] = useState(1);
  const [form, setForm] = useState(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subFor, setSubFor] = useState<string | null>(null);
  const [subForm, setSubForm] = useState(EMPTY_SUB);
  const [subBusy, setSubBusy] = useState(false);
  const [editFor, setEditFor] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(EMPTY_EDIT);
  const [editBusy, setEditBusy] = useState(false);
  const [tiers, setTiers] = useState<VoiceTier[]>([]);
  const [services, setServices] = useState<ServiceTypeInfo[]>([]);

  const load = useCallback(() => {
    api<Page<AdminMerchant>>(`/api/admin/merchants?page=${page}&page_size=${PAGE_SIZE}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page]);

  useEffect(load, [load]);

  useEffect(() => {
    api<Plan[]>("/api/admin/plans").then(setPlans).catch(() => {});
    api<VoiceTier[]>("/api/public/voice-tiers").then(setTiers).catch(() => {});
    api<ServiceTypeInfo[]>("/api/public/service-types").then(setServices).catch(() => {});
  }, []);

  const set = (key: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const setSub = (key: string) => (e: { target: { value: string } }) =>
    setSubForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/admin/merchants", { method: "POST", body: form });
      setForm(EMPTY);
      setShowForm(false);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function toggleActive(merchant: AdminMerchant) {
    setError("");
    try {
      await api(`/api/admin/merchants/${merchant.id}`, {
        method: "PATCH",
        body: { active: !merchant.active },
      });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function resetPassword(merchant: AdminMerchant) {
    const password = prompt(t('"{name}"-এর নতুন পাসওয়ার্ড:', { name: merchant.business_name }));
    if (!password) return;
    setError("");
    try {
      await api(`/api/admin/merchants/${merchant.id}`, { method: "PATCH", body: { password } });
      alert(t("পাসওয়ার্ড পরিবর্তন হয়েছে"));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function openSubEditor(merchant: AdminMerchant) {
    setEditFor(null);
    if (subFor === merchant.id) {
      setSubFor(null);
      return;
    }
    setSubFor(merchant.id);
    setSubForm({
      ...EMPTY_SUB,
      plan_key: merchant.plan_key ?? "",
      status: merchant.sub_status ?? "",
    });
  }

  function openEditor(merchant: AdminMerchant) {
    setSubFor(null);
    if (editFor === merchant.id) {
      setEditFor(null);
      return;
    }
    setEditFor(merchant.id);
    setEditForm({
      business_name: merchant.business_name,
      owner_name: merchant.owner_name,
      phone: merchant.phone,
      email: merchant.email,
      support_phone: merchant.support_phone,
      custom_greeting: merchant.custom_greeting,
      max_call_seconds: merchant.max_call_seconds,
      voice_tier: merchant.voice_tier || "very_basic",
      service_type: merchant.service_type || "ecommerce",
    });
  }

  const setEdit = (key: string) => (e: { target: { value: string } }) =>
    setEditForm((f) => ({ ...f, [key]: e.target.value }));

  async function saveEdit(e: FormEvent, merchant: AdminMerchant) {
    e.preventDefault();
    setError("");
    setEditBusy(true);
    try {
      await api(`/api/admin/merchants/${merchant.id}`, { method: "PATCH", body: editForm });
      setEditFor(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEditBusy(false);
    }
  }

  async function saveSub(e: FormEvent, merchant: AdminMerchant) {
    e.preventDefault();
    setError("");
    setSubBusy(true);
    const body: Record<string, unknown> = {};
    if (subForm.plan_key) body.plan_key = subForm.plan_key;
    if (subForm.status) body.status = subForm.status;
    if (subForm.bonus_calls !== "") body.bonus_calls = Number(subForm.bonus_calls);
    if (subForm.bonus_minutes !== "") body.bonus_minutes = Number(subForm.bonus_minutes);
    if (subForm.extend_days !== "") body.extend_days = Number(subForm.extend_days);
    if (subForm.note) body.note = subForm.note;
    try {
      await api(`/api/admin/merchants/${merchant.id}/subscription`, { method: "PATCH", body });
      setSubFor(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubBusy(false);
    }
  }

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>{t("মার্চেন্ট অ্যাকাউন্ট")}</h1>
        <span className="spacer" />
        <button className="btn" onClick={() => setShowForm((s) => !s)}>
          {showForm ? t("বন্ধ করুন") : t("+ নতুন মার্চেন্ট")}
        </button>
      </div>
      {error && <p className="error">{t(error)}</p>}
      {showForm && (
        <form className="card form" style={{ marginBottom: 16 }} onSubmit={submit}>
          <div className="form-row">
            <label>{t("সার্ভিস টাইপ * (কোন ফ্লো-তে কল হবে)")}</label>
            <select value={form.service_type} onChange={set("service_type")}>
              {services.map((service) => (
                <option key={service.key} value={service.key}>
                  {service.icon} {t(service.name_bn)} — {t(service.description_bn)}
                </option>
              ))}
            </select>
          </div>
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
            <label>{t("পাসওয়ার্ড *")}</label>
            <input value={form.password} onChange={set("password")} required />
          </div>
          <div className="form-row">
            <label>{t("ফোন")}</label>
            <input value={form.phone} onChange={set("phone")} />
          </div>
          <div className="form-row">
            <label>{t("ইমেইল")}</label>
            <input type="email" value={form.email} onChange={set("email")} />
          </div>
          <div className="form-row">
            <label>{t("সাপোর্ট নম্বর (কাস্টমার মানুষ চাইলে এই নম্বরে কল যাবে)")}</label>
            <input value={form.support_phone} onChange={set("support_phone")} placeholder="01712345678" />
          </div>
          <button className="btn">{t("তৈরি করুন")}</button>
        </form>
      )}
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("ব্যবসা")}</th>
              <th>{t("সার্ভিস")}</th>
              <th>{t("মালিক")}</th>
              <th>{t("ইউজারনেম")}</th>
              <th>{t("সাপোর্ট নম্বর")}</th>
              <th>{t("প্ল্যান")}</th>
              <th>{t("কল ব্যবহার")}</th>
              <th>{t("অবস্থা")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((merchant) => (
              <Fragment key={merchant.id}>
                <tr>
                  <td>{merchant.business_name}</td>
                  <td>
                    {merchant.service_type === "courier" ? "📦 " : "🛍️ "}
                    {t(SERVICE_LABELS[merchant.service_type] ?? merchant.service_type)}
                  </td>
                  <td>{merchant.owner_name || "—"}</td>
                  <td>{merchant.username}</td>
                  <td>{merchant.support_phone || "—"}</td>
                  <td>
                    {merchant.plan_name_bn ? t(merchant.plan_name_bn) : "—"}{" "}
                    {merchant.sub_status && (
                      <span className={`badge ${merchant.sub_status}`}>
                        {t(SUB_STATUS_LABELS[merchant.sub_status as SubStatus] ?? merchant.sub_status)}
                      </span>
                    )}
                  </td>
                  <td className="muted">
                    {fmtNum(merchant.calls_used)}/{fmtNum(merchant.call_limit)}
                  </td>
                  <td>
                    <span className={`badge ${merchant.active ? "active" : "inactive"}`}>
                      {merchant.active ? t("সক্রিয়") : t("নিষ্ক্রিয়")}
                    </span>
                  </td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <button className="btn secondary small" onClick={() => openEditor(merchant)}>
                      ✏️ {t("সম্পাদনা")}
                    </button>
                    <button className="btn secondary small" onClick={() => openSubEditor(merchant)}>
                      {t("সাবস্ক্রিপশন")}
                    </button>
                    <button className="btn secondary small" onClick={() => toggleActive(merchant)}>
                      {merchant.active ? t("নিষ্ক্রিয় করুন") : t("সক্রিয় করুন")}
                    </button>
                    <button className="btn secondary small" onClick={() => resetPassword(merchant)}>
                      {t("পাসওয়ার্ড রিসেট")}
                    </button>
                  </td>
                </tr>
                {editFor === merchant.id && (
                  <tr>
                    <td colSpan={9} style={{ background: "#fafbfc" }}>
                      <form
                        className="form"
                        style={{ maxWidth: "none", padding: "8px 0" }}
                        onSubmit={(e) => saveEdit(e, merchant)}
                      >
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
                          <div className="form-row">
                            <label>{t("সার্ভিস টাইপ")}</label>
                            <select
                              value={editForm.service_type}
                              onChange={setEdit("service_type")}
                              style={{ width: 150 }}
                            >
                              {services.map((service) => (
                                <option key={service.key} value={service.key}>
                                  {service.icon} {t(service.name_bn)}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-row">
                            <label>{t("ব্যবসার নাম *")}</label>
                            <input
                              value={editForm.business_name}
                              onChange={setEdit("business_name")}
                              required
                              style={{ width: 180 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("মালিকের নাম")}</label>
                            <input
                              value={editForm.owner_name}
                              onChange={setEdit("owner_name")}
                              style={{ width: 150 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("ফোন")}</label>
                            <input value={editForm.phone} onChange={setEdit("phone")} style={{ width: 140 }} />
                          </div>
                          <div className="form-row">
                            <label>{t("ইমেইল")}</label>
                            <input
                              type="email"
                              value={editForm.email}
                              onChange={setEdit("email")}
                              style={{ width: 180 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("সাপোর্ট নম্বর")}</label>
                            <input
                              value={editForm.support_phone}
                              onChange={setEdit("support_phone")}
                              style={{ width: 140 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("ভয়েস কোয়ালিটি")}</label>
                            <select
                              value={editForm.voice_tier}
                              onChange={setEdit("voice_tier")}
                              style={{ width: 160 }}
                            >
                              {tiers.map((tier) => (
                                <option key={tier.key} value={tier.key}>
                                  {t(tier.name_bn)}
                                  {tier.accent_bn ? ` · ${t(tier.accent_bn)}` : ""}
                                  {` (×${tier.multiplier})`}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-row">
                            <label>{t("এক কলের সর্বোচ্চ সময়")}</label>
                            <select
                              value={editForm.max_call_seconds}
                              onChange={(e) =>
                                setEditForm((f) => ({
                                  ...f,
                                  max_call_seconds: Number(e.target.value),
                                }))
                              }
                              style={{ width: 150 }}
                            >
                              {DURATION_CHOICES.map((secs) => (
                                <option key={secs} value={secs}>
                                  {secs === 0
                                    ? t("ডিফল্ট (৪ মিনিট)")
                                    : t("{n} মিনিট", { n: fmtNum(secs / 60) })}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-row" style={{ flex: 1, minWidth: 220 }}>
                            <label>{t("কলের শুরুর কথা (সর্বোচ্চ ২০০ অক্ষর)")}</label>
                            <input
                              maxLength={200}
                              value={editForm.custom_greeting}
                              onChange={setEdit("custom_greeting")}
                            />
                          </div>
                          <button className="btn small" disabled={editBusy}>
                            {editBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ")}
                          </button>
                        </div>
                      </form>
                    </td>
                  </tr>
                )}
                {subFor === merchant.id && (
                  <tr>
                    <td colSpan={9} style={{ background: "#fafbfc" }}>
                      <form
                        className="form"
                        style={{ maxWidth: "none", padding: "8px 0" }}
                        onSubmit={(e) => saveSub(e, merchant)}
                      >
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
                          <div className="form-row">
                            <label>{t("প্ল্যান")}</label>
                            <select value={subForm.plan_key} onChange={setSub("plan_key")}>
                              <option value="">{t("— অপরিবর্তিত —")}</option>
                              {plans.map((p) => (
                                <option key={p.key} value={p.key}>
                                  {t(p.name_bn)} ({p.key})
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-row">
                            <label>{t("স্ট্যাটাস")}</label>
                            <select value={subForm.status} onChange={setSub("status")}>
                              <option value="">{t("— অপরিবর্তিত —")}</option>
                              {Object.entries(SUB_STATUS_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>
                                  {t(label)}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-row">
                            <label>{t("বোনাস কল")}</label>
                            <input
                              type="number"
                              value={subForm.bonus_calls}
                              onChange={setSub("bonus_calls")}
                              style={{ width: 110 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("বোনাস মিনিট")}</label>
                            <input
                              type="number"
                              value={subForm.bonus_minutes}
                              onChange={setSub("bonus_minutes")}
                              style={{ width: 110 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("মেয়াদ বাড়ান (দিন)")}</label>
                            <input
                              type="number"
                              value={subForm.extend_days}
                              onChange={setSub("extend_days")}
                              style={{ width: 110 }}
                            />
                          </div>
                          <div className="form-row" style={{ flex: 1, minWidth: 180 }}>
                            <label>{t("নোট")}</label>
                            <input value={subForm.note} onChange={setSub("note")} />
                          </div>
                          <button className="btn small" disabled={subBusy}>
                            {subBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ")}
                          </button>
                        </div>
                      </form>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={9}>
                  <EmptyState art={<GreetingArt />} title={t("কোনো মার্চেন্ট নেই")} />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />}
    </>
  );
}
