import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { AdminCall, Page } from "../../api/types";
import EmptyState from "../../components/EmptyState";
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

export default function AdminCalls() {
  const { t, fmtDateTime } = useLang();
  const [data, setData] = useState<Page<AdminCall> | null>(null);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Page<AdminCall>>(`/api/admin/calls?page=${page}&page_size=${PAGE_SIZE}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <>
      <h1 className="page-title">{t("সব কল")}</h1>
      {error && <p className="error">{t(error)}</p>}
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
                  <td>{call.outcome || "—"}</td>
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
