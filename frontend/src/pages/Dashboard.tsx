import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, auth } from "../api/client";
import { BillingSummary, CallInsights, STATUS_LABELS, OrderStatus } from "../api/types";
import { GreetingArt } from "../components/art";
import { DailyOutcomeChart, OutcomeBreakdown } from "../components/InsightsCharts";
import { useLang } from "../i18n";
import { serviceText, useServiceType } from "../service";

type Stats = Record<string, number>;

export default function Dashboard() {
  const { t, fmtNum, fmtDate } = useLang();
  const service = useServiceType();
  const labels = serviceText(service);
  const [stats, setStats] = useState<Stats | null>(null);
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const [insights, setInsights] = useState<CallInsights | null>(null);

  useEffect(() => {
    api<Stats>("/api/orders/stats").then(setStats).catch(() => {});
    api<BillingSummary>("/api/billing/summary").then(setBilling).catch(() => {});
    api<CallInsights>("/api/orders/insights").then(setInsights).catch(() => {});
    const timer = setInterval(() => api<Stats>("/api/orders/stats").then(setStats).catch(() => {}), 10000);
    return () => clearInterval(timer);
  }, []);

  const keys: OrderStatus[] =
    service === "courier"
      ? ["pending", "calling", "confirmed", "rescheduled", "cancelled", "no_answer", "needs_review"]
      : ["pending", "calling", "confirmed", "cancelled", "no_answer", "needs_review"];

  const sub = billing?.subscription;
  const usage = billing?.usage;
  const nearLimit =
    usage != null && usage.call_limit > 0 && usage.calls_used >= usage.call_limit * 0.9;

  const num = (v?: number) => (v == null ? "—" : fmtNum(v));

  return (
    <>
      <div className="card hero-card">
        <div className="hero-text">
          <h2>{t("স্বাগতম, {name}!", { name: auth.name ?? "" })}</h2>
          <p className="muted">{t(labels.heroLine)}</p>
          <p style={{ marginTop: 12 }}>
            <Link className="btn" to="/orders/new">
              + {t(labels.newItem)}
            </Link>
          </p>
        </div>
        <GreetingArt />
      </div>
      {billing && sub?.status === "trialing" && (
        <div className="banner">
          {t("ফ্রি ট্রায়াল চলছে — শেষ হবে {date}।", {
            date: fmtDate(sub.current_period_end),
          })}{" "}
          <Link to="/billing">{t("প্ল্যান দেখুন")}</Link>
        </div>
      )}
      {billing && (!sub || sub.status === "past_due" || sub.status === "canceled") && (
        <div className="banner danger">
          {t("সাবস্ক্রিপশন সক্রিয় নেই — কল করা বন্ধ।")} <Link to="/billing">{t("বিলিং পেজে যান")}</Link>
        </div>
      )}
      {nearLimit && (
        <div className="banner warn">
          {t("কল সীমা প্রায় শেষ ({used}/{limit})।", {
            used: fmtNum(usage!.calls_used),
            limit: fmtNum(usage!.call_limit),
          })}{" "}
          <Link to="/billing">{t("প্ল্যান আপগ্রেড করুন")}</Link>
        </div>
      )}
      <div className="stats-grid">
        <div className="card stat">
          <div className="num">{num(stats?.total)}</div>
          <div className="label">{t(labels.totalLabel)}</div>
        </div>
        {keys.map((k) => (
          <div className="card stat" key={k}>
            <div className="num">{num(stats?.[k])}</div>
            <div className="label">{t(STATUS_LABELS[k])}</div>
          </div>
        ))}
      </div>
      {insights && (
        <>
          <h2 className="page-title" style={{ fontSize: 17, marginTop: 4 }}>
            {t("গত ৩০ দিনের কল ইনসাইট")}
          </h2>
          <div className="stats-grid">
            <div className="card stat">
              <div className="num">{fmtNum(insights.totals.calls)}</div>
              <div className="label">{t("মোট কল")}</div>
            </div>
            <div className="card stat">
              <div className="num">{fmtNum(insights.totals.picked)}</div>
              <div className="label">
                {t("ধরেছেন")}{" "}
                <span className="muted">({fmtNum(insights.totals.pickup_rate)}%)</span>
              </div>
            </div>
            <div className="card stat">
              <div className="num">{fmtNum(insights.totals.confirmed)}</div>
              <div className="label">
                <span className="legend-dot" style={{ background: "#0d9488" }} /> {t("নিশ্চিত")}
              </div>
            </div>
            <div className="card stat">
              <div className="num">{fmtNum(insights.totals.cancelled)}</div>
              <div className="label">
                <span className="legend-dot" style={{ background: "#e34948" }} /> {t("বাতিল")}
              </div>
            </div>
            <div className="card stat">
              <div className="num">{fmtNum(insights.totals.no_answer)}</div>
              <div className="label">
                <span className="legend-dot" style={{ background: "#6d5cc9" }} /> {t("ধরেননি")}
              </div>
            </div>
            <div className="card stat">
              <div className="num">{fmtNum(insights.totals.avg_duration_secs)}</div>
              <div className="label">{t("গড় কল (সেকেন্ড)")}</div>
            </div>
          </div>
          {insights.totals.calls === 0 ? (
            <div className="card" style={{ marginBottom: 16 }}>
              <p className="muted">
                {t("এই সময়ে কোনো কল হয়নি — অর্ডারে “কল করুন” চাপলেই এখানে ইনসাইট জমা হবে।")}
              </p>
            </div>
          ) : (
            <div className="finance-cols">
              <div className="card">
                <DailyOutcomeChart data={insights} />
              </div>
              <div className="card">
                <OutcomeBreakdown data={insights} />
              </div>
            </div>
          )}
        </>
      )}
      <div className="card">
        <p>
          {t("নতুন অর্ডার যোগ করতে")} <Link to="/orders/new">{t("এখানে ক্লিক করুন")}</Link>
          {t("। অর্ডার তালিকা থেকে")} <b>“{t("কল করুন")}”</b>{" "}
          {t("চাপলেই এজেন্ট কাস্টমারকে ফোন করে বাংলায় অর্ডার নিশ্চিত করবে, এবং ফলাফল স্বয়ংক্রিয়ভাবে এখানে আপডেট হবে।")}
        </p>
      </div>
    </>
  );
}
