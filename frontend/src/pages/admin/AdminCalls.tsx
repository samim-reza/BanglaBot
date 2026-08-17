import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { AdminCall, AdminCallSummary, OUTCOME_LABELS, Page } from "../../api/types";
import EmptyState from "../../components/EmptyState";
import MerchantSelect from "../../components/MerchantSelect";
import Pagination from "../../components/Pagination";
import { CallsArt } from "../../components/art";
import RecordingPlayer from "../../components/RecordingPlayer";
import { useLang } from "../../i18n";

const PAGE_SIZE = 20;

function fmtDuration(secs: number) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

const mins = (secs: number) => Math.ceil(secs / 60);

export default function AdminCalls() {
  const { t, fmtNum, fmtMoney, fmtDateTime } = useLang();
  const [data, setData] = useState<Page<AdminCall> | null>(null);
  const [summary, setSummary] = useState<AdminCallSummary | null>(null);
  const [page, setPage] = useState(1);
  const [merchantId, setMerchantId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");

  const filterParams = useCallback(() => {
    const params = new URLSearchParams();
    if (merchantId) params.set("merchant_id", merchantId);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    return params;
  }, [merchantId, dateFrom, dateTo]);

  const load = useCallback(() => {
    const params = filterParams();
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    api<Page<AdminCall>>(`/api/admin/calls?${params}`)
      .then(setData)
      .catch((e) => setError(e.message));
    api<AdminCallSummary>(`/api/admin/calls/summary?${filterParams()}`)
      .then(setSummary)
      .catch(() => {});
  }, [page, filterParams]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const resetPage = () => setPage(1);

  return (
    <>
      <h1 className="page-title">{t("সব কল")}</h1>
      {error && <p className="error">{t(error)}</p>}
      <div className="toolbar">
        <MerchantSelect
          value={merchantId}
          onChange={(id) => {
            setMerchantId(id);
            resetPage();
          }}
        />
        <label className="muted">{t("শুরুর তারিখ")}</label>
        <input
          type="date"
          value={dateFrom}
          max={dateTo || undefined}
          onChange={(e) => {
            setDateFrom(e.target.value);
            resetPage();
          }}
        />
        <label className="muted">{t("শেষ তারিখ")}</label>
        <input
          type="date"
          value={dateTo}
          min={dateFrom || undefined}
          onChange={(e) => {
            setDateTo(e.target.value);
            resetPage();
          }}
        />
        {(merchantId || dateFrom || dateTo) && (
          <button
            className="btn secondary small"
            onClick={() => {
              setMerchantId("");
              setDateFrom("");
              setDateTo("");
              resetPage();
            }}
          >
            {t("ফিল্টার মুছুন")}
          </button>
        )}
      </div>

      <div className="stats-grid">
        <div className="card stat">
          <div className="num">{summary ? fmtNum(summary.totals.calls) : "—"}</div>
          <div className="label">{t("মোট কল")}</div>
        </div>
        <div className="card stat">
          <div className="num">{summary ? fmtNum(mins(summary.totals.duration_secs)) : "—"}</div>
          <div className="label">{t("মোট কথার মিনিট")}</div>
        </div>
        <div className="card stat">
          <div className="num">{summary ? fmtNum(mins(summary.totals.billed_secs)) : "—"}</div>
          <div className="label">{t("বিলড মিনিট")}</div>
        </div>
        <div className="card stat">
          <div className="num">{summary ? fmtMoney(summary.totals.cost_bdt.toFixed(2)) : "—"}</div>
          <div className="label">{t("মোট খরচ")}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("মার্চেন্ট অনুযায়ী কল ও খরচ")}</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("মার্চেন্ট")}</th>
                <th>{t("কল")}</th>
                <th>{t("মিনিট")}</th>
                <th>{t("বিলড মিনিট")}</th>
                <th>{t("খরচ")}</th>
              </tr>
            </thead>
            <tbody>
              {summary?.merchants.map((row) => (
                <tr
                  key={row.merchant_id}
                  onClick={() => {
                    setMerchantId(row.merchant_id === merchantId ? "" : row.merchant_id);
                    resetPage();
                  }}
                  style={{ cursor: "pointer" }}
                  title={t("এই মার্চেন্টের কল দেখতে ক্লিক করুন")}
                >
                  <td>{row.merchant_name}</td>
                  <td>{fmtNum(row.calls)}</td>
                  <td>{fmtNum(mins(row.duration_secs))}</td>
                  <td>{fmtNum(mins(row.billed_secs))}</td>
                  <td>{fmtMoney(row.cost_bdt.toFixed(2))}</td>
                </tr>
              ))}
              {summary && summary.merchants.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>
                    {t("এই সময়ে কোনো কল হয়নি")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("সময়")}</th>
              <th>{t("মার্চেন্ট")}</th>
              <th>{t("অর্ডার")}</th>
              <th>{t("স্ট্যাটাস")}</th>
              <th>{t("ফলাফল")}</th>
              <th>{t("সময়কাল")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((call) => (
              <Fragment key={call.id}>
                <tr>
                  <td className="muted">{fmtDateTime(call.created_at)}</td>
                  <td>{call.merchant_name}</td>
                  <td>{call.order_ref || call.order_id?.slice(0, 8) || "—"}</td>
                  <td>{call.call_status || "—"}</td>
                  <td>{call.outcome ? t(OUTCOME_LABELS[call.outcome] ?? call.outcome) : "—"}</td>
                  <td className="muted">{fmtDuration(call.duration_secs)}</td>
                  <td>
                    <button
                      className="btn secondary small"
                      onClick={() => setExpanded((cur) => (cur === call.id ? null : call.id))}
                    >
                      {expanded === call.id ? t("বন্ধ করুন") : t("বিস্তারিত")}
                    </button>
                  </td>
                </tr>
                {expanded === call.id && (
                  <tr>
                    <td colSpan={7} style={{ whiteSpace: "normal" }}>
                      {call.recording_sid && (
                        <p style={{ marginBottom: 8 }}>
                          <RecordingPlayer path={`/api/admin/recordings/${call.id}`} />
                        </p>
                      )}
                      {call.transcript ? (
                        <pre className="transcript">{call.transcript}</pre>
                      ) : (
                        <p className="muted">{t("কোনো ট্রান্সক্রিপ্ট নেই")}</p>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    art={<CallsArt />}
                    title={t("কোনো কল নেই")}
                    hint={t("মার্চেন্টরা কল শুরু করলে এখানে রেকর্ডিংসহ দেখা যাবে")}
                  />
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
