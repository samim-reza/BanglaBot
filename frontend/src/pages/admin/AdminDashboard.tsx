import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { AdminStats, OrderStatus, STATUS_LABELS } from "../../api/types";
import { useLang } from "../../i18n";

export default function AdminDashboard() {
  const { t, fmtNum, fmtMoney, fmtDateTime } = useLang();
  const [stats, setStats] = useState<AdminStats | null>(null);

  useEffect(() => {
    const load = () => api<AdminStats>("/api/admin/stats").then(setStats).catch(() => {});
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  const keys: OrderStatus[] = ["pending", "calling", "confirmed", "cancelled", "no_answer", "needs_review"];

  return (
    <>
      <h1 className="page-title">{t("প্ল্যাটফর্ম ড্যাশবোর্ড")}</h1>
      <div className="stats-grid">
        <div className="card stat">
          <div className="num">
            {stats ? `${fmtNum(stats.merchants.active)}/${fmtNum(stats.merchants.total)}` : "—"}
          </div>
          <div className="label">{t("মার্চেন্ট (সক্রিয়/মোট)")}</div>
        </div>
        <div className="card stat">
          <div className="num">{stats ? fmtMoney(stats.mrr) : "—"}</div>
          <div className="label">MRR</div>
        </div>
        <div className="card stat">
          <div className="num">{stats ? fmtNum(stats.calls_month.calls) : "—"}</div>
          <div className="label">{t("এ মাসের কল")}</div>
        </div>
        <div className="card stat">
          <div className="num">{stats ? fmtNum(stats.calls_month.minutes) : "—"}</div>
          <div className="label">{t("এ মাসের মিনিট")}</div>
        </div>
        <div className="card stat">
          <div className="num">{stats ? fmtNum(stats.open_tickets) : "—"}</div>
          <div className="label">{t("খোলা টিকিট")}</div>
        </div>
        <div className="card stat">
          <div className="num">{stats ? fmtNum(stats.due_invoices) : "—"}</div>
          <div className="label">{t("বকেয়া ইনভয়েস")}</div>
        </div>
      </div>
      <div className="stats-grid">
        <div className="card stat">
          <div className="num">{stats?.orders.total != null ? fmtNum(stats.orders.total) : "—"}</div>
          <div className="label">{t("মোট অর্ডার")}</div>
        </div>
        {keys.map((k) => (
          <div className="card stat" key={k}>
            <div className="num">{stats?.orders[k] != null ? fmtNum(stats.orders[k]!) : "—"}</div>
            <div className="label">{t(STATUS_LABELS[k])}</div>
          </div>
        ))}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div className="card">
          <h2 className="page-title" style={{ fontSize: 17, marginBottom: 12 }}>
            {t("প্ল্যান অনুযায়ী মার্চেন্ট")}
          </h2>
          {stats && stats.plans.length === 0 && <p className="muted">{t("কোনো সাবস্ক্রিপশন নেই")}</p>}
          <div style={{ display: "grid", gap: 8 }}>
            {stats?.plans.map((p) => (
              <div key={p.key} style={{ display: "flex", justifyContent: "space-between", fontSize: 14.5 }}>
                <span>{t(p.name_bn)}</span>
                <b>{fmtNum(p.count)}</b>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h2 className="page-title" style={{ fontSize: 17, marginBottom: 12 }}>
            {t("সাম্প্রতিক কার্যকলাপ")}
          </h2>
          {stats && stats.recent_logs.length === 0 && <p className="muted">{t("কোনো কার্যকলাপ নেই")}</p>}
          <div style={{ display: "grid", gap: 10 }}>
            {stats?.recent_logs.map((log) => (
              <div key={log.id} style={{ fontSize: 14 }}>
                <p>{t(log.detail || log.action)}</p>
                <p className="muted" style={{ fontSize: 12.5 }}>
                  {fmtDateTime(log.created_at)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
