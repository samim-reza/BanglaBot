import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { FLOW_DATA_LABELS, OrderDetail as OrderDetailType, OUTCOME_LABELS } from "../api/types";
import RecordingPlayer from "../components/RecordingPlayer";
import StatusBadge from "../components/StatusBadge";
import { useLang } from "../i18n";
import { CALLABLE_STATUSES, serviceText, useServiceType } from "../service";

interface EditForm {
  order_ref: string;
  customer_name: string;
  customer_phone: string;
  address: string;
  items_summary: string;
  total_amount: string;
  notes: string;
}

export default function OrderDetail() {
  const { t, fmtNum, fmtMoney, fmtDateTime } = useLang();
  const labels = serviceText(useServiceType());
  const { id } = useParams();
  const [order, setOrder] = useState<OrderDetailType | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api<OrderDetailType>(`/api/orders/${id}`).then(setOrder).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [load]);

  async function startCall() {
    setError("");
    try {
      await api(`/api/orders/${id}/call`, { method: "POST" });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function beginEdit() {
    if (!order) return;
    setForm({
      order_ref: order.order_ref,
      customer_name: order.customer_name,
      customer_phone: order.customer_phone,
      address: order.address,
      items_summary: order.items_summary,
      total_amount: String(order.total_amount),
      notes: order.notes,
    });
    setEditing(true);
    setError("");
  }

  const setField = (key: keyof EditForm) => (e: { target: { value: string } }) =>
    setForm((f) => (f ? { ...f, [key]: e.target.value } : f));

  async function saveEdit(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setError("");
    setSaving(true);
    try {
      await api(`/api/orders/${id}`, {
        method: "PATCH",
        body: { ...form, total_amount: Number(form.total_amount || 0) },
      });
      setEditing(false);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!order) return <p className="muted">{t(error || "লোড হচ্ছে...")}</p>;

  return (
    <>
      <p style={{ marginBottom: 10 }}>
        <Link to="/orders">← {t(labels.backLabel)}</Link>
      </p>
      <h1 className="page-title">
        {t(labels.noun)} {order.order_ref || order.id.slice(0, 8)} <StatusBadge status={order.status} />
      </h1>
      {error && <p className="error">{t(error)}</p>}
      <div className="card" style={{ marginBottom: 16 }}>
        {editing && form ? (
          <form className="form" onSubmit={saveEdit}>
            <div className="form-row">
              <label>{t(labels.refLabel)}</label>
              <input value={form.order_ref} onChange={setField("order_ref")} />
            </div>
            <div className="form-row">
              <label>{t(labels.customerLabel)}</label>
              <input value={form.customer_name} onChange={setField("customer_name")} required />
            </div>
            <div className="form-row">
              <label>{t("ফোন নম্বর *")}</label>
              <input value={form.customer_phone} onChange={setField("customer_phone")} required />
            </div>
            <div className="form-row">
              <label>{t("ঠিকানা")}</label>
              <textarea rows={2} value={form.address} onChange={setField("address")} />
            </div>
            <div className="form-row">
              <label>{t(labels.itemsLabel)}</label>
              <textarea rows={2} value={form.items_summary} onChange={setField("items_summary")} />
            </div>
            <div className="form-row">
              <label>{t(labels.amountLabel)}</label>
              <input
                type="number" min="0" step="0.01"
                value={form.total_amount} onChange={setField("total_amount")}
              />
            </div>
            <div className="form-row">
              <label>{t("নোট")}</label>
              <textarea rows={2} value={form.notes} onChange={setField("notes")} />
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn" disabled={saving}>
                {saving ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ করুন")}
              </button>
              <button type="button" className="btn secondary" onClick={() => setEditing(false)}>
                {t("বাতিল")}
              </button>
            </div>
          </form>
        ) : (
          <>
            <dl className="detail-grid">
              <dt>{t(labels.customerShort)}</dt>
              <dd>{order.customer_name}</dd>
              <dt>{t("ফোন")}</dt>
              <dd>{order.customer_phone}</dd>
              <dt>{t("ঠিকানা")}</dt>
              <dd>{order.address || "—"}</dd>
              <dt>{t(labels.itemsShort)}</dt>
              <dd>{order.items_summary || "—"}</dd>
              <dt>{t(labels.amountShort)}</dt>
              <dd>{fmtMoney(order.total_amount)}</dd>
              <dt>{t("নোট")}</dt>
              <dd style={{ whiteSpace: "pre-wrap" }}>{order.notes || "—"}</dd>
              <dt>{t("কল হয়েছে")}</dt>
              <dd>{t("{n} বার", { n: fmtNum(order.call_attempts) })}</dd>
            </dl>
            <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
              {CALLABLE_STATUSES.includes(order.status) && (
                <button className="btn" onClick={startCall}>
                  📞 {t(labels.callButton)}
                </button>
              )}
              {order.status !== "calling" && (
                <button className="btn secondary" onClick={beginEdit}>
                  ✏️ {t(labels.editButton)}
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {Object.keys(order.flow_data ?? {}).length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 className="page-title" style={{ fontSize: 16 }}>
            🤖 {t("কল থেকে পাওয়া তথ্য")}
          </h2>
          <dl className="detail-grid">
            {Object.entries(order.flow_data).map(([key, value]) => (
              <span key={key} style={{ display: "contents" }}>
                <dt>{t(FLOW_DATA_LABELS[key] ?? key)}</dt>
                <dd>
                  {typeof value === "boolean" ? (value ? t("হ্যাঁ") : t("না")) : String(value)}
                </dd>
              </span>
            ))}
          </dl>
        </div>
      )}

      <h2 className="page-title" style={{ fontSize: 17 }}>
        {t("কলের ইতিহাস")}
      </h2>
      {order.call_logs.length === 0 && <p className="muted">{t("এখনো কোনো কল হয়নি।")}</p>}
      {order.call_logs.map((log) => (
        <div className="card" key={log.id} style={{ marginBottom: 12 }}>
          <p style={{ marginBottom: 8 }}>
            <b>{fmtDateTime(log.created_at)}</b>{" "}
            <span className="muted">
              — {t("স্ট্যাটাস")}: {log.call_status}
              {log.outcome && <> — {t("ফলাফল")}: {t(OUTCOME_LABELS[log.outcome] ?? log.outcome)}</>}
              {log.duration_secs > 0 && <> — {t("{n} সেকেন্ড", { n: fmtNum(log.duration_secs) })}</>}
            </span>
          </p>
          {log.recording_sid && (
            <p style={{ marginBottom: 8 }}>
              <RecordingPlayer path={`/api/orders/recordings/${log.id}`} />
            </p>
          )}
          {log.transcript ? (
            <div className="transcript">{log.transcript}</div>
          ) : (
            <p className="muted">{t("ট্রান্সক্রিপ্ট নেই")}</p>
          )}
        </div>
      ))}
    </>
  );
}
