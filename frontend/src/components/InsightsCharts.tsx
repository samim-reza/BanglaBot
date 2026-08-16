import { useState } from "react";
import { CallInsights, InsightsDay } from "../api/types";
import { useLang } from "../i18n";

/**
 * Series palette (validated for CVD safety on the white card surface with
 * scripts/validate_palette.js — adjacent ΔE ≥ 11.9). Amber sits below 3:1
 * contrast, so the chart always ships a legend and a table view.
 */
const SERIES: { key: keyof Omit<InsightsDay, "day">; label: string; color: string }[] = [
  { key: "confirmed", label: "নিশ্চিত", color: "#0d9488" },
  { key: "cancelled", label: "বাতিল", color: "#e34948" },
  { key: "no_answer", label: "ধরেননি", color: "#6d5cc9" },
  { key: "other", label: "অন্যান্য", color: "#eda100" },
];

function dayTotal(d: InsightsDay): number {
  return d.confirmed + d.cancelled + d.no_answer + d.other;
}

function Legend() {
  const { t } = useLang();
  return (
    <div className="chart-legend">
      {SERIES.map((s) => (
        <span key={s.key} className="legend-item">
          <span className="legend-dot" style={{ background: s.color }} />
          {t(s.label)}
        </span>
      ))}
    </div>
  );
}

/** Stacked daily columns: one bar per day, segments per call outcome. */
export function DailyOutcomeChart({ data }: { data: CallInsights }) {
  const { t, fmtNum, fmtDate } = useLang();
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  const days = data.daily;
  const max = Math.max(...days.map(dayTotal), 1);
  const niceMax = max <= 4 ? 4 : Math.ceil(max / 4) * 4;

  const W = 640;
  const H = 230;
  const PAD_L = 8;
  const PAD_B = 22;
  const plotH = H - PAD_B - 10;
  const step = (W - PAD_L) / days.length;
  const barW = Math.max(5, step - 4);

  if (asTable) {
    const withCalls = days.filter((d) => dayTotal(d) > 0);
    return (
      <>
        <div className="toolbar" style={{ marginBottom: 8 }}>
          <span className="muted" style={{ fontSize: 13 }}>{t("দৈনিক কল ও ফলাফল")}</span>
          <span className="spacer" />
          <button className="btn secondary small" onClick={() => setAsTable(false)}>
            {t("চার্ট দেখুন")}
          </button>
        </div>
        <div className="table-wrap" style={{ maxHeight: 280, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>{t("তারিখ")}</th>
                <th>{t("মোট")}</th>
                {SERIES.map((s) => (
                  <th key={s.key}>{t(s.label)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {withCalls.map((d) => (
                <tr key={d.day}>
                  <td>{fmtDate(d.day)}</td>
                  <td><b>{fmtNum(dayTotal(d))}</b></td>
                  {SERIES.map((s) => (
                    <td key={s.key} className="muted">{fmtNum(d[s.key])}</td>
                  ))}
                </tr>
              ))}
              {withCalls.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted" style={{ textAlign: "center" }}>
                    {t("এই সময়ে কোনো কল হয়নি")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  const hovered = hover !== null ? days[hover] : null;
  return (
    <div style={{ position: "relative" }}>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <span className="muted" style={{ fontSize: 13 }}>{t("দৈনিক কল ও ফলাফল")}</span>
        <span className="spacer" />
        <button className="btn secondary small" onClick={() => setAsTable(true)}>
          {t("টেবিল দেখুন")}
        </button>
      </div>
      {hovered && dayTotal(hovered) > 0 && (
        <div
          className="chart-tip"
          style={{ left: `${((PAD_L + (hover! + 0.5) * step) / W) * 100}%` }}
        >
          <b>{fmtDate(hovered.day)}</b> — {t("{n}টি কল", { n: fmtNum(dayTotal(hovered)) })}
          {SERIES.filter((s) => hovered[s.key] > 0).map((s) => (
            <span key={s.key}>
              <br />
              {t(s.label)}: {fmtNum(hovered[s.key])}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line
              x1={PAD_L} x2={W}
              y1={10 + plotH * (1 - f)} y2={10 + plotH * (1 - f)}
              stroke="#eef1f4" strokeWidth="1"
            />
            <text x={W - 2} y={10 + plotH * (1 - f) - 3} textAnchor="end" fontSize="10" fill="#6b7280">
              {fmtNum(Math.round(niceMax * f))}
            </text>
          </g>
        ))}
        <line x1={PAD_L} x2={W} y1={10 + plotH} y2={10 + plotH} stroke="#e3e8ec" strokeWidth="1" />
        {days.map((d, i) => {
          const x = PAD_L + i * step + (step - barW) / 2;
          const dayNum = Number(d.day.slice(8));
          let y = 10 + plotH; // running top of the stack
          const segments: { color: string; y: number; h: number }[] = [];
          for (const s of SERIES) {
            const value = d[s.key];
            if (value === 0) continue;
            const h = (value / niceMax) * plotH;
            y -= h;
            segments.push({ color: s.color, y, h });
          }
          const top = segments[segments.length - 1];
          return (
            <g key={d.day}>
              <rect
                x={PAD_L + i * step} y={10} width={step} height={plotH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
              {segments.map((seg, j) => {
                const dim = hover === null || hover === i ? 1 : 0.45;
                if (seg === top) {
                  // Rounded data-end; full height so the stack reads to its true total.
                  const h = Math.max(seg.h, 2.5);
                  return (
                    <path
                      key={j}
                      d={`M${x} ${seg.y + seg.h} v${-(h - 2)} q0 -2 2 -2 h${barW - 4} q2 0 2 2 v${h - 2} z`}
                      fill={seg.color} opacity={dim} pointerEvents="none"
                    />
                  );
                }
                // 1.5px surface gap above each lower segment; base stays anchored.
                return (
                  <rect
                    key={j}
                    x={x} y={seg.y + 1.5} width={barW} height={Math.max(seg.h - 1.5, 1)}
                    fill={seg.color} opacity={dim} pointerEvents="none"
                  />
                );
              })}
              {(dayNum === 1 || dayNum % 5 === 0) && (
                <text
                  x={PAD_L + (i + 0.5) * step} y={H - 6}
                  textAnchor="middle" fontSize="10" fill="#6b7280"
                >
                  {fmtNum(dayNum)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <Legend />
    </div>
  );
}

/** Horizontal share-of-outcome bars plus pickup / confirmation meters. */
export function OutcomeBreakdown({ data }: { data: CallInsights }) {
  const { t, fmtNum } = useLang();
  const totals = data.totals;
  const max = Math.max(totals.confirmed, totals.cancelled, totals.no_answer, totals.other, 1);
  const rows = SERIES.map((s) => ({ ...s, value: totals[s.key] }));

  return (
    <>
      <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>{t("ফলাফলের ভাগ")}</p>
      <div style={{ display: "grid", gap: 10 }}>
        {rows.map((row) => (
          <div key={row.key}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
              <span>
                <span className="legend-dot" style={{ background: row.color }} /> {t(row.label)}
              </span>
              <b>
                {fmtNum(row.value)}
                <span className="muted" style={{ fontWeight: 400 }}>
                  {" "}({fmtNum(totals.calls ? Math.round((row.value * 100) / totals.calls) : 0)}%)
                </span>
              </b>
            </div>
            <div className="progress" style={{ marginTop: 4 }}>
              <span style={{ width: `${(row.value / max) * 100}%`, background: row.color }} />
            </div>
          </div>
        ))}
      </div>
      <div className="rate-row">
        <div className="rate-box">
          <div className="rate-num">{fmtNum(totals.pickup_rate)}%</div>
          <div className="muted" style={{ fontSize: 12.5 }}>{t("পিকআপ রেট")}</div>
        </div>
        <div className="rate-box">
          <div className="rate-num">{fmtNum(totals.confirm_rate)}%</div>
          <div className="muted" style={{ fontSize: 12.5 }}>{t("কনফার্ম রেট (ধরাদের মধ্যে)")}</div>
        </div>
        <div className="rate-box">
          <div className="rate-num">{fmtNum(totals.minutes)}</div>
          <div className="muted" style={{ fontSize: 12.5 }}>{t("মোট কথার মিনিট")}</div>
        </div>
      </div>
    </>
  );
}
