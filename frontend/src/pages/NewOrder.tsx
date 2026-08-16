import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useLang } from "../i18n";

export default function NewOrder() {
  const { t } = useLang();
  const [form, setForm] = useState({
    order_ref: "",
    customer_name: "",
    customer_phone: "",
    address: "",
    items_summary: "",
    total_amount: "",
    notes: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const set = (key: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/api/orders", {
        method: "POST",
        body: { ...form, total_amount: Number(form.total_amount || 0) },
      });
      navigate("/orders");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="page-title">{t("নতুন অর্ডার")}</h1>
      <form className="card form" onSubmit={submit}>
        <div className="form-row">
          <label>{t("অর্ডার নম্বর (ঐচ্ছিক)")}</label>
          <input value={form.order_ref} onChange={set("order_ref")} placeholder="ORD-1001" />
        </div>
        <div className="form-row">
          <label>{t("কাস্টমারের নাম *")}</label>
          <input value={form.customer_name} onChange={set("customer_name")} required />
        </div>
        <div className="form-row">
          <label>{t("ফোন নম্বর *")}</label>
          <input value={form.customer_phone} onChange={set("customer_phone")} placeholder="01712345678" required />
        </div>
        <div className="form-row">
          <label>{t("ঠিকানা")}</label>
          <textarea rows={2} value={form.address} onChange={set("address")} />
        </div>
        <div className="form-row">
          <label>{t("পণ্যের বিবরণ")}</label>
          <textarea rows={2} value={form.items_summary} onChange={set("items_summary")} placeholder={t("পাঞ্জাবি (L) x১, শাড়ি x২")} />
        </div>
        <div className="form-row">
          <label>{t("মোট মূল্য (টাকা)")}</label>
          <input type="number" min="0" step="0.01" value={form.total_amount} onChange={set("total_amount")} />
        </div>
        <div className="form-row">
          <label>{t("নোট")}</label>
          <textarea rows={2} value={form.notes} onChange={set("notes")} />
        </div>
        {error && <div className="error">{t(error)}</div>}
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn" disabled={busy}>
            {busy ? t("সংরক্ষণ হচ্ছে...") : t("অর্ডার সংরক্ষণ করুন")}
          </button>
          <button type="button" className="btn secondary" onClick={() => navigate("/orders")}>
            {t("বাতিল")}
          </button>
        </div>
      </form>
    </>
  );
}
