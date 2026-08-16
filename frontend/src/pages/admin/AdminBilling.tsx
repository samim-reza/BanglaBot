import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { AdminInvoice, AdminMerchant, INVOICE_STATUS_LABELS, InvoiceStatus, Page } from "../../api/types";
import Pagination from "../../components/Pagination";
import { useLang } from "../../i18n";

const PAGE_SIZE = 20;

export default function AdminBilling() {
  const { t, fmtDate, fmtMoney } = useLang();
  const [data, setData] = useState<Page<AdminInvoice> | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [merchants, setMerchants] = useState<AdminMerchant[]>([]);
  const [genFor, setGenFor] = useState("");
  const [showGen, setShowGen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status) params.set("status", status);
    api<Page<AdminInvoice>>(`/api/admin/invoices?${params}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page, status]);

  useEffect(load, [load]);

  useEffect(() => {
    // Page through every merchant — the API caps page_size at 100.
    let stale = false;
    (async () => {
      const all: AdminMerchant[] = [];
      for (let p = 1; ; p++) {
        const res = await api<Page<AdminMerchant>>(
          `/api/admin/merchants?page=${p}&page_size=100`
        );
        all.push(...res.items);
        if (all.length >= res.total || res.items.length === 0) break;
      }
      if (!stale) setMerchants(all);
    })().catch(() => {});
    return () => {
      stale = true;
    };
  }, []);

  async function generate(e: FormEvent) {
    e.preventDefault();
    if (!genFor) return;
    setError("");
    setBusy(true);
    try {
      await api("/api/admin/invoices/generate", { method: "POST", body: { merchant_id: genFor } });
      setShowGen(false);
      setGenFor("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function update(invoice: AdminInvoice, body: { status: string; payment_method?: string }) {
    setError("");
    try {
      await api(`/api/admin/invoices/${invoice.id}`, { method: "PATCH", body });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>{t("ইনভয়েস")}</h1>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("সব স্ট্যাটাস")}</option>
          {Object.entries(INVOICE_STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {t(label)}
            </option>
          ))}
        </select>
        <span className="spacer" />
        <button className="btn" onClick={() => setShowGen((s) => !s)}>
          {showGen ? t("বন্ধ করুন") : t("ইনভয়েস তৈরি")}
        </button>
      </div>
      {error && <p className="error">{t(error)}</p>}
      {showGen && (
        <form className="card form" style={{ marginBottom: 16 }} onSubmit={generate}>
          <div className="form-row">
            <label>{t("মার্চেন্ট *")}</label>
            <select value={genFor} onChange={(e) => setGenFor(e.target.value)} required>
              <option value="">{t("— মার্চেন্ট বাছাই করুন —")}</option>
              {merchants.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.business_name}
                </option>
              ))}
            </select>
          </div>
          <button className="btn" disabled={busy || !genFor}>
            {busy ? t("তৈরি হচ্ছে...") : t("তৈরি করুন")}
          </button>
        </form>
      )}
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("নম্বর")}</th>
              <th>{t("মার্চেন্ট")}</th>
              <th>{t("সময়কাল")}</th>
              <th>{t("পরিমাণ")}</th>
              <th>{t("স্ট্যাটাস")}</th>
              <th>{t("পেমেন্ট")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((inv) => (
              <tr key={inv.id}>
                <td>{inv.number}</td>
                <td>{inv.merchant_name}</td>
                <td className="muted">
                  {fmtDate(inv.period_start)} —{" "}
                  {fmtDate(inv.period_end)}
                </td>
                <td>{fmtMoney(inv.amount_due)}</td>
                <td>
                  <span className={`badge ${inv.status}`}>
                    {t(INVOICE_STATUS_LABELS[inv.status as InvoiceStatus] ?? inv.status)}
                  </span>
                </td>
                <td className="muted">{inv.payment_method || "—"}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  {inv.status === "due" && (
                    <>
                      <button
                        className="btn small"
                        onClick={() => update(inv, { status: "paid", payment_method: "bkash" })}
                      >
                        {t("পরিশোধিত করুন")}
                      </button>
                      <button className="btn secondary small" onClick={() => update(inv, { status: "void" })}>
                        {t("বাতিল")}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={7} className="muted" style={{ textAlign: "center", padding: 30 }}>
                  {t("কোনো ইনভয়েস নেই")}
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
