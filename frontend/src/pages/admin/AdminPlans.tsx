import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { Plan } from "../../api/types";
import { useLang } from "../../i18n";

const EMPTY = {
  key: "",
  name_bn: "",
  price_monthly: "0",
  max_calls_per_month: "0",
  max_minutes_per_month: "0",
  features: "",
  trial_days: "0",
  active: true,
  sort_order: "0",
};

export default function AdminPlans() {
  const { t, fmtNum, fmtMoney } = useLang();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Plan[]>("/api/admin/plans").then(setPlans).catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const set = (key: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  function startCreate() {
    setEditingId(null);
    setForm(EMPTY);
    setShowForm(true);
  }

  function startEdit(plan: Plan) {
    setEditingId(plan.id);
    setForm({
      key: plan.key,
      name_bn: plan.name_bn,
      price_monthly: String(plan.price_monthly),
      max_calls_per_month: String(plan.max_calls_per_month),
      max_minutes_per_month: String(plan.max_minutes_per_month),
      features: plan.features.join("\n"),
      trial_days: String(plan.trial_days),
      active: plan.active,
      sort_order: String(plan.sort_order),
    });
    setShowForm(true);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    const body: Record<string, unknown> = {
      name_bn: form.name_bn,
      price_monthly: Number(form.price_monthly),
      max_calls_per_month: Number(form.max_calls_per_month),
      max_minutes_per_month: Number(form.max_minutes_per_month),
      features: form.features
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      trial_days: Number(form.trial_days),
      active: form.active,
      sort_order: Number(form.sort_order),
    };
    try {
      if (editingId) {
        await api(`/api/admin/plans/${editingId}`, { method: "PATCH", body });
      } else {
        await api("/api/admin/plans", { method: "POST", body: { ...body, key: form.key } });
      }
      setShowForm(false);
      setForm(EMPTY);
      setEditingId(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>{t("প্ল্যান")}</h1>
        <span className="spacer" />
        <button className="btn" onClick={() => (showForm ? setShowForm(false) : startCreate())}>
          {showForm ? t("বন্ধ করুন") : t("+ নতুন প্ল্যান")}
        </button>
      </div>
      {error && <p className="error">{t(error)}</p>}
      {showForm && (
        <form className="card form" style={{ marginBottom: 16 }} onSubmit={submit}>
          <h2 className="page-title" style={{ fontSize: 17, marginBottom: 0 }}>
            {editingId ? t("প্ল্যান সম্পাদনা") : t("নতুন প্ল্যান")}
          </h2>
          {!editingId && (
            <div className="form-row">
              <label>{t("কী (ইংরেজি, যেমন starter) *")}</label>
              <input value={form.key} onChange={set("key")} required />
            </div>
          )}
          <div className="form-row">
            <label>{t("নাম *")}</label>
            <input value={form.name_bn} onChange={set("name_bn")} required />
          </div>
          <div className="form-row">
            <label>{t("মাসিক মূল্য (৳)")}</label>
            <input type="number" value={form.price_monthly} onChange={set("price_monthly")} />
          </div>
          <div className="form-row">
            <label>{t("মাসিক কল সীমা")}</label>
            <input type="number" value={form.max_calls_per_month} onChange={set("max_calls_per_month")} />
          </div>
          <div className="form-row">
            <label>{t("মাসিক মিনিট সীমা")}</label>
            <input type="number" value={form.max_minutes_per_month} onChange={set("max_minutes_per_month")} />
          </div>
          <div className="form-row">
            <label>{t("ফিচার (প্রতি লাইনে একটি)")}</label>
            <textarea rows={4} value={form.features} onChange={set("features")} />
          </div>
          <div className="form-row">
            <label>{t("ট্রায়াল দিন")}</label>
            <input type="number" value={form.trial_days} onChange={set("trial_days")} />
          </div>
          <div className="form-row">
            <label>{t("ক্রম (sort)")}</label>
            <input type="number" value={form.sort_order} onChange={set("sort_order")} />
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14.5 }}>
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
              style={{ width: "auto" }}
            />
            {t("সক্রিয়")}
          </label>
          <button className="btn" disabled={busy}>
            {busy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
          </button>
        </form>
      )}
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("নাম")}</th>
              <th>{t("কী")}</th>
              <th>{t("মূল্য")}</th>
              <th>{t("কল সীমা")}</th>
              <th>{t("মিনিট সীমা")}</th>
              <th>{t("ট্রায়াল দিন")}</th>
              <th>{t("সক্রিয়")}</th>
              <th>{t("অর্ডার")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id}>
                <td>{t(plan.name_bn)}</td>
                <td className="muted">{plan.key}</td>
                <td>{fmtMoney(plan.price_monthly)}</td>
                <td>{fmtNum(plan.max_calls_per_month)}</td>
                <td>{fmtNum(plan.max_minutes_per_month)}</td>
                <td>{fmtNum(plan.trial_days)}</td>
                <td>
                  <span className={`badge ${plan.active ? "active" : "inactive"}`}>
                    {plan.active ? t("সক্রিয়") : t("নিষ্ক্রিয়")}
                  </span>
                </td>
                <td className="muted">{fmtNum(plan.sort_order)}</td>
                <td>
                  <button className="btn secondary small" onClick={() => startEdit(plan)}>
                    {t("সম্পাদনা")}
                  </button>
                </td>
              </tr>
            ))}
            {plans.length === 0 && (
              <tr>
                <td colSpan={9} className="muted" style={{ textAlign: "center", padding: 30 }}>
                  {t("কোনো প্ল্যান নেই")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
