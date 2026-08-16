import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import {
  BillingSummary,
  Invoice,
  INVOICE_STATUS_LABELS,
  Page,
  Plan,
  SUB_STATUS_LABELS,
} from "../api/types";
import EmptyState from "../components/EmptyState";
import Pagination from "../components/Pagination";
import { InvoicesArt, WalletArt } from "../components/art";
import { useLang } from "../i18n";

const PAGE_SIZE = 10;

function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const { fmtNum } = useLang();
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
        <span>{label}</span>
        <span className="muted">
          {fmtNum(used)} / {fmtNum(limit)}
        </span>
      </div>
      <div className="progress">
        <span className={pct >= 90 ? "warn" : ""} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function Billing() {
  const { t, fmtNum, fmtMoney, fmtDate } = useLang();
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [invoices, setInvoices] = useState<Page<Invoice> | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadSummary = useCallback(() => {
    api<BillingSummary>("/api/billing/summary").then(setSummary).catch((e) => setError(e.message));
  }, []);

  const loadInvoices = useCallback(() => {
    api<Page<Invoice>>(`/api/billing/invoices?page=${page}&page_size=${PAGE_SIZE}`)
      .then(setInvoices)
      .catch((e) => setError(e.message));
  }, [page]);

  useEffect(() => {
    loadSummary();
    api<Plan[]>("/api/billing/plans").then(setPlans).catch((e) => setError(e.message));
  }, [loadSummary]);

  useEffect(() => {
    loadInvoices();
  }, [loadInvoices]);

  async function changePlan(plan: Plan) {
    if (
      !window.confirm(
        t("{plan} প্ল্যানে যেতে চান? মাসিক ফি {price}", {
          plan: t(plan.name_bn),
          price: fmtMoney(plan.price_monthly),
        })
      )
    )
      return;
    setError("");
    setBusy(true);
    try {
      const res = await api<BillingSummary>("/api/billing/change-plan", {
        method: "POST",
        body: { plan_key: plan.key },
      });
      setSummary(res);
      loadInvoices();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!summary) return <p className="muted">{t(error || "লোড হচ্ছে...")}</p>;

  const sub = summary.subscription;
  const plan = summary.plan;
  const usage = summary.usage;
  const trialDaysLeft =
    sub?.status === "trialing"
      ? Math.max(0, Math.ceil((new Date(sub.current_period_end).getTime() - Date.now()) / 86400000))
      : null;
  const subInactive = !sub || sub.status === "past_due" || sub.status === "canceled";

  return (
    <>
      <h1 className="page-title">{t("বিলিং")}</h1>
      {error && <p className="error">{t(error)}</p>}

      {subInactive && (
        <div className="banner danger">
          {t("সাবস্ক্রিপশন সক্রিয় নেই — কল করা বন্ধ। নিচ থেকে একটি প্ল্যান নিন।")}
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <h2 className="page-title" style={{ fontSize: 17, marginBottom: 12 }}>
          {t("বর্তমান প্ল্যান")}
        </h2>
        {sub && plan ? (
          <div style={{ display: "grid", gap: 8 }}>
            <p>
              <b>{t(plan.name_bn)}</b>{" "}
              <span className={`badge ${sub.status}`}>{t(SUB_STATUS_LABELS[sub.status])}</span>
            </p>
            <p>
              {fmtMoney(plan.price_monthly)}
              {t("/মাস")}
            </p>
            <p className="muted">
              {t("সময়কাল")}: {fmtDate(sub.current_period_start)} —{" "}
              {fmtDate(sub.current_period_end)}
            </p>
            {trialDaysLeft !== null && (
              <p className="muted">
                {t("ট্রায়াল শেষ হতে বাকি {n} দিন", { n: fmtNum(trialDaysLeft) })}
              </p>
            )}
          </div>
        ) : (
          <p className="muted">{t("কোনো সাবস্ক্রিপশন নেই।")}</p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 16, display: "grid", gap: 14 }}>
        <h2 className="page-title" style={{ fontSize: 17, marginBottom: 0 }}>
          {t("এই মাসের ব্যবহার")}
        </h2>
        <Meter label={t("কল")} used={usage.calls_used} limit={usage.call_limit} />
        <Meter label={t("মিনিট")} used={usage.minutes_used} limit={usage.minute_limit} />
      </div>

      <h2 className="page-title" style={{ fontSize: 17 }}>
        {t("প্ল্যানসমূহ")}
      </h2>
      <div className="plan-grid" style={{ marginBottom: 16 }}>
        {plans
          .filter((p) => p.trial_days === 0)
          .map((p) => {
            const isCurrent = sub?.plan_key === p.key && sub?.status === "active";
            return (
              <div className={`plan-card ${isCurrent ? "current" : ""}`} key={p.id}>
                <b>{t(p.name_bn)}</b>
                <div className="price">
                  {fmtMoney(p.price_monthly)}
                  <span className="muted" style={{ fontSize: 14, fontWeight: 400 }}>{t("/মাস")}</span>
                </div>
                <ul style={{ paddingInlineStart: 18, display: "grid", gap: 4, fontSize: 14 }}>
                  {p.features.map((f, i) => (
                    <li key={i}>{t(f)}</li>
                  ))}
                </ul>
                {isCurrent ? (
                  <span className="badge active">{t("বর্তমান প্ল্যান")}</span>
                ) : (
                  <button className="btn" disabled={busy} onClick={() => changePlan(p)}>
                    {t("এই প্ল্যানে যান")}
                  </button>
                )}
              </div>
            );
          })}
      </div>

      {summary.bkash_number && (
        <div className="card" style={{ marginBottom: 16, display: "flex", gap: 18, alignItems: "center" }}>
          <WalletArt />
          <div>
            <p style={{ fontWeight: 600, marginBottom: 4 }}>{t("যেভাবে পেমেন্ট করবেন")}</p>
            <p>
              {t("পেমেন্ট: বিকাশ")} <b>{summary.bkash_number}</b> {t("নম্বরে পাঠিয়ে সাপোর্টে জানান")}
            </p>
          </div>
        </div>
      )}

      <h2 className="page-title" style={{ fontSize: 17 }}>
        {t("ইনভয়েস")}
      </h2>
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("নম্বর")}</th>
              <th>{t("সময়কাল")}</th>
              <th>{t("পরিমাণ")}</th>
              <th>{t("স্ট্যাটাস")}</th>
              <th>{t("তারিখ")}</th>
            </tr>
          </thead>
          <tbody>
            {invoices?.items.map((inv) => (
              <tr key={inv.id}>
                <td>{inv.number}</td>
                <td>
                  {fmtDate(inv.period_start)} — {fmtDate(inv.period_end)}
                </td>
                <td>{fmtMoney(inv.amount_due)}</td>
                <td>
                  <span className={`badge ${inv.status}`}>{t(INVOICE_STATUS_LABELS[inv.status])}</span>
                </td>
                <td className="muted">{fmtDate(inv.created_at)}</td>
              </tr>
            ))}
            {invoices && invoices.items.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState
                    art={<InvoicesArt />}
                    title={t("কোনো ইনভয়েস নেই")}
                    hint={t("প্ল্যান নিলে ইনভয়েস এখানে দেখা যাবে")}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {invoices && (
        <Pagination page={page} pageSize={PAGE_SIZE} total={invoices.total} onChange={setPage} />
      )}
    </>
  );
}
