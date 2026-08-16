import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { CostRateItem, FinanceOverview } from "../../api/types";
import { FinanceArt } from "../../components/art";
import { useLang } from "../../i18n";

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Single-series daily-cost column chart with per-bar tooltip and table view. */
function DailyCostChart({ month, daily }: { month: string; daily: FinanceOverview["daily"] }) {
  const { t, fmtNum, fmtMoney, fmtDate } = useLang();
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  const [yearS, monthS] = month.split("-");
  const daysInMonth = new Date(Number(yearS), Number(monthS), 0).getDate();
  const byDay = new Map(daily.map((d) => [Number(d.day.slice(8)), d]));
  const series = Array.from({ length: daysInMonth }, (_, i) => ({
    day: i + 1,
    cost: byDay.get(i + 1)?.cost_bdt ?? 0,
    calls: byDay.get(i + 1)?.calls ?? 0,
  }));
  const max = Math.max(...series.map((d) => d.cost), 1);
  const niceMax = Math.ceil(max / 100) * 100 || 100;

  const W = 640;
  const H = 210;
  const PAD_L = 8;
  const PAD_B = 22;
  const plotH = H - PAD_B - 8;
  const step = (W - PAD_L) / daysInMonth;
  const barW = Math.max(4, step - 2);

  if (asTable) {
    return (
      <>
        <div className="toolbar" style={{ marginBottom: 8 }}>
          <span className="spacer" />
          <button className="btn secondary small" onClick={() => setAsTable(false)}>
            {t("চার্ট দেখুন")}
          </button>
        </div>
        <div className="table-wrap" style={{ maxHeight: 260, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>{t("তারিখ")}</th>
                <th>{t("খরচ")}</th>
                <th>{t("কল")}</th>
              </tr>
            </thead>
            <tbody>
              {series.filter((d) => d.calls > 0).map((d) => (
                <tr key={d.day}>
                  <td>{fmtDate(`${month}-${String(d.day).padStart(2, "0")}`)}</td>
                  <td>{fmtMoney(d.cost.toFixed(2))}</td>
                  <td>{fmtNum(d.calls)}</td>
                </tr>
              ))}
              {series.every((d) => d.calls === 0) && (
                <tr>
                  <td colSpan={3} className="muted" style={{ textAlign: "center" }}>
                    {t("এ মাসে কোনো কল খরচ নেই")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  const hovered = hover !== null ? series[hover] : null;
  return (
    <div style={{ position: "relative" }}>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <span className="muted" style={{ fontSize: 13 }}>
          {t("দৈনিক কল খরচ (৳)")}
        </span>
        <span className="spacer" />
        <button className="btn secondary small" onClick={() => setAsTable(true)}>
          {t("টেবিল দেখুন")}
        </button>
      </div>
      {hovered && hovered.calls > 0 && (
        <div
          className="chart-tip"
          style={{
            left: `${((PAD_L + (hovered.day - 0.5) * step) / W) * 100}%`,
          }}
        >
          <b>{fmtDate(`${month}-${String(hovered.day).padStart(2, "0")}`)}</b>
          <br />
          {fmtMoney(hovered.cost.toFixed(2))} · {t("{n}টি কল", { n: fmtNum(hovered.calls) })}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line
              x1={PAD_L}
              x2={W}
              y1={8 + plotH * (1 - f)}
              y2={8 + plotH * (1 - f)}
              stroke="#eef1f4"
              strokeWidth="1"
            />
            <text x={W - 2} y={8 + plotH * (1 - f) - 3} textAnchor="end" fontSize="10" fill="#6b7280">
              ৳{fmtNum(Math.round(niceMax * f))}
            </text>
          </g>
        ))}
        <line x1={PAD_L} x2={W} y1={8 + plotH} y2={8 + plotH} stroke="#e3e8ec" strokeWidth="1" />
        {series.map((d, i) => {
          const h = Math.max(d.cost > 0 ? 3 : 0, (d.cost / niceMax) * plotH);
          const x = PAD_L + i * step + (step - barW) / 2;
          return (
            <g key={d.day}>
              {/* generous invisible hit target */}
              <rect
                x={PAD_L + i * step}
                y={8}
                width={step}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
              {h > 0 && (
                <path
                  d={`M${x} ${8 + plotH} v${-(h - 3)} q0 -3 3 -3 h${barW - 6} q3 0 3 3 v${h - 3} z`}
                  fill={hover === i ? "#0f766e" : "#0d9488"}
                  pointerEvents="none"
                />
              )}
              {(d.day === 1 || d.day % 5 === 0) && (
                <text
                  x={PAD_L + (i + 0.5) * step}
                  y={H - 6}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#6b7280"
                >
                  {fmtNum(d.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function AdminFinance() {
  const { t, fmtNum, fmtMoney } = useLang();
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState<FinanceOverview | null>(null);
  const [rates, setRates] = useState<CostRateItem[]>([]);
  const [rateEdits, setRateEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [whatIf, setWhatIf] = useState({ merchants: "10", minutes: "450", price: "4000" });

  const load = useCallback(() => {
    api<FinanceOverview>(`/api/admin/finance/overview?month=${month}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [month]);

  useEffect(load, [load]);

  useEffect(() => {
    api<CostRateItem[]>("/api/admin/finance/rates").then(setRates).catch(() => {});
  }, []);

  async function saveRate(rate: CostRateItem) {
    const value = rateEdits[rate.cost_key];
    if (value === undefined || value === "" || Number(value) === Number(rate.rate_bdt)) return;
    setError("");
    setNotice("");
    try {
      const updated = await api<CostRateItem[]>("/api/admin/finance/rates", {
        method: "POST",
        body: { cost_key: rate.cost_key, rate_bdt: Number(value) },
      });
      setRates(updated);
      setRateEdits((e) => ({ ...e, [rate.cost_key]: "" }));
      setNotice(t("নতুন রেট সংরক্ষিত — এখন থেকে কার্যকর, পুরনো হিসাব বদলায়নি"));
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const wiMerchants = Number(whatIf.merchants) || 0;
  const wiMinutes = Number(whatIf.minutes) || 0;
  const wiPrice = Number(whatIf.price) || 0;
  const perMin = data?.unit.cost_per_minute_bdt ?? 0;
  const wiRevenue = wiMerchants * wiPrice;
  const wiCost = wiMerchants * wiMinutes * perMin + (data?.costs.fixed_bdt ?? 0);
  const wiMargin = wiRevenue - wiCost;

  const breakdown = data
    ? [
        { label: "টেলিফোনি (Twilio)", value: data.costs.telephony_bdt },
        { label: "টিটিএস — ভয়েস (ElevenLabs)", value: data.costs.tts_bdt },
        { label: "এলএলএম (OpenAI)", value: data.costs.llm_bdt },
        { label: "এসটিটি — স্পিচ টু টেক্সট (OpenAI)", value: data.costs.stt_bdt },
        { label: "নির্দিষ্ট মাসিক খরচ (সার্ভার/ডেটাবেস)", value: data.costs.fixed_bdt },
      ]
    : [];
  const breakdownMax = Math.max(...breakdown.map((b) => b.value), 1);

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>
          {t("ফাইন্যান্স")}
        </h1>
        <span className="spacer" />
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
      </div>
      {error && <p className="error">{t(error)}</p>}
      {notice && <p className="banner">{notice}</p>}

      <div className="stats-grid">
        <div className="card stat">
          <div className="num">{data ? fmtMoney(data.revenue.mrr) : "—"}</div>
          <div className="label">{t("এমআরআর (সক্রিয় সাবস্ক্রিপশন)")}</div>
        </div>
        <div className="card stat">
          <div className="num">{data ? fmtMoney(data.revenue.collected) : "—"}</div>
          <div className="label">{t("এ মাসে আদায়")}</div>
        </div>
        <div className="card stat">
          <div className="num">{data ? fmtMoney(data.costs.total_bdt.toFixed(0)) : "—"}</div>
          <div className="label">{t("মোট খরচ (কল + নির্দিষ্ট)")}</div>
        </div>
        <div className="card stat">
          <div className="num" style={{ color: data && data.margin.gross_bdt < 0 ? "#dc2626" : "#0f766e" }}>
            {data ? fmtMoney(data.margin.gross_bdt.toFixed(0)) : "—"}
          </div>
          <div className="label">
            {t("গ্রস মার্জিন (আদায় − খরচ)")} {data ? `(${fmtNum(data.margin.pct.toFixed(0))}%)` : ""}
          </div>
        </div>
        <div className="card stat">
          <div className="num">{data ? fmtNum(data.calls.count) : "—"}</div>
          <div className="label">{t("কল")}</div>
        </div>
        <div className="card stat">
          <div className="num">{data ? fmtNum(data.calls.minutes.toFixed(0)) : "—"}</div>
          <div className="label">{t("মিনিট")}</div>
        </div>
        <div className="card stat">
          <div className="num">{data ? fmtMoney(data.calls.avg_cost_bdt.toFixed(2)) : "—"}</div>
          <div className="label">{t("গড় খরচ / কল")}</div>
        </div>
        <div className="card stat">
          <div className="num">{data ? fmtMoney(data.revenue.outstanding) : "—"}</div>
          <div className="label">{t("বকেয়া ইনভয়েস (মোট)")}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        {data && <DailyCostChart month={data.month} daily={data.daily} />}
      </div>

      <div className="finance-cols">
        <div className="card">
          <h2 className="page-title" style={{ fontSize: 16 }}>
            {t("খরচের খাত (এ মাস)")}
          </h2>
          <div style={{ display: "grid", gap: 10 }}>
            {breakdown.map((b) => (
              <div key={b.label}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
                  <span>{t(b.label)}</span>
                  <b>{fmtMoney(b.value.toFixed(2))}</b>
                </div>
                <div className="progress" style={{ marginTop: 4 }}>
                  <span style={{ width: `${(b.value / breakdownMax) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
            {t("প্রতি সংযুক্ত মিনিটের খরচ")}: <b>{fmtMoney(perMin.toFixed(2))}</b>
          </p>
        </div>

        <div className="card">
          <div style={{ display: "flex", gap: 12, alignItems: "start" }}>
            <div style={{ flex: 1 }}>
              <h2 className="page-title" style={{ fontSize: 16 }}>
                {t("খরচের রেট (এখন থেকে কার্যকর)")}
              </h2>
              <p className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                {t("রেট বদলালে নতুন কলে নতুন রেট লাগে — পুরনো কলের হিসাব অপরিবর্তিত থাকে।")}
              </p>
            </div>
            <FinanceArt />
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {rates.map((rate) => (
              <div key={rate.cost_key} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ flex: 1, fontSize: 13.5 }}>
                  {t(rate.label_bn)}{" "}
                  <span className="muted">
                    ({rate.unit === "per_month" ? t("প্রতি মাস") : t("প্রতি মিনিট")})
                  </span>
                </span>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  style={{ width: 110 }}
                  placeholder={String(rate.rate_bdt)}
                  value={rateEdits[rate.cost_key] ?? ""}
                  onChange={(e) =>
                    setRateEdits((edits) => ({ ...edits, [rate.cost_key]: e.target.value }))
                  }
                />
                <button className="btn secondary small" onClick={() => saveRate(rate)}>
                  {t("সংরক্ষণ")}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="finance-cols">
        <div className="card">
          <h2 className="page-title" style={{ fontSize: 16 }}>
            {t("কী হলে কী হবে (প্রজেকশন)")}
          </h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div className="form-row">
              <label>{t("মার্চেন্ট সংখ্যা")}</label>
              <input
                type="number"
                min="0"
                style={{ width: 110 }}
                value={whatIf.merchants}
                onChange={(e) => setWhatIf((w) => ({ ...w, merchants: e.target.value }))}
              />
            </div>
            <div className="form-row">
              <label>{t("গড় মিনিট / মার্চেন্ট")}</label>
              <input
                type="number"
                min="0"
                style={{ width: 110 }}
                value={whatIf.minutes}
                onChange={(e) => setWhatIf((w) => ({ ...w, minutes: e.target.value }))}
              />
            </div>
            <div className="form-row">
              <label>{t("মাসিক প্ল্যান মূল্য (৳)")}</label>
              <input
                type="number"
                min="0"
                style={{ width: 110 }}
                value={whatIf.price}
                onChange={(e) => setWhatIf((w) => ({ ...w, price: e.target.value }))}
              />
            </div>
          </div>
          <div className="stats-grid" style={{ marginTop: 12, marginBottom: 0 }}>
            <div className="card stat">
              <div className="num">{fmtMoney(wiRevenue)}</div>
              <div className="label">{t("আনুমানিক আয়")}</div>
            </div>
            <div className="card stat">
              <div className="num">{fmtMoney(wiCost.toFixed(0))}</div>
              <div className="label">{t("আনুমানিক খরচ")}</div>
            </div>
            <div className="card stat">
              <div className="num" style={{ color: wiMargin < 0 ? "#dc2626" : "#0f766e" }}>
                {fmtMoney(wiMargin.toFixed(0))}
              </div>
              <div className="label">
                {t("আনুমানিক মার্জিন")}{" "}
                {wiRevenue > 0 ? `(${fmtNum(((wiMargin / wiRevenue) * 100).toFixed(0))}%)` : ""}
              </div>
            </div>
          </div>
        </div>

        <div className="card table-wrap" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>{t("মার্চেন্ট")}</th>
                <th>{t("প্ল্যান")}</th>
                <th>{t("আয়")}</th>
                <th>{t("খরচ")}</th>
                <th>{t("মার্জিন")}</th>
                <th>{t("কল")}</th>
                <th>{t("মিনিট")}</th>
              </tr>
            </thead>
            <tbody>
              {data?.per_merchant.map((row) => (
                <tr key={row.merchant_id}>
                  <td>{row.merchant_name}</td>
                  <td>{row.plan_name_bn ? t(row.plan_name_bn) : "—"}</td>
                  <td>{fmtMoney(row.revenue_bdt)}</td>
                  <td>{fmtMoney(row.cost_bdt.toFixed(2))}</td>
                  <td style={{ color: row.margin_bdt < 0 ? "#dc2626" : "#0f766e" }}>
                    {fmtMoney(row.margin_bdt.toFixed(2))}
                  </td>
                  <td className="muted">{fmtNum(row.calls)}</td>
                  <td className="muted">{fmtNum(row.minutes.toFixed(1))}</td>
                </tr>
              ))}
              {data && data.per_merchant.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted" style={{ textAlign: "center", padding: 24 }}>
                    {t("এ মাসে কোনো কল খরচ নেই")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
