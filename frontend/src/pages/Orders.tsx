import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Order, OrderStatus, Page, STATUS_LABELS } from "../api/types";
import EmptyState from "../components/EmptyState";
import Pagination from "../components/Pagination";
import { BoxArt } from "../components/art";
import StatusBadge from "../components/StatusBadge";
import { useLang } from "../i18n";

const PAGE_SIZE = 15;

export default function Orders() {
  const { t, fmtNum, fmtMoney } = useLang();
  const [data, setData] = useState<Page<Order> | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  const load = useCallback((isStale?: () => boolean) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    api<Page<Order>>(`/api/orders?${params}`)
      .then((d) => {
        if (!isStale?.()) setData(d);
      })
      .catch((e) => setError(e.message));
  }, [page, status, search]);

  useEffect(() => {
    // Filters retrigger this effect; the stale flag drops slow out-of-date responses.
    let stale = false;
    const run = () => load(() => stale);
    run();
    const timer = setInterval(run, 8000); // live refresh while calls run
    return () => {
      stale = true;
      clearInterval(timer);
    };
  }, [load]);

  async function startCall(id: string) {
    setError("");
    try {
      await api(`/api/orders/${id}/call`, { method: "POST" });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <h1 className="page-title">{t("অর্ডারসমূহ")}</h1>
      <div className="toolbar">
        <input
          placeholder={t("নাম / ফোন / অর্ডার নম্বর খুঁজুন")}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          style={{ width: 260 }}
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("সব স্ট্যাটাস")}</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {t(label)}
            </option>
          ))}
        </select>
        <span className="spacer" />
        <Link to="/orders/new" className="btn">
          + {t("নতুন অর্ডার")}
        </Link>
      </div>
      {error && <p className="error">{t(error)}</p>}
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("অর্ডার")}</th>
              <th>{t("কাস্টমার")}</th>
              <th>{t("ফোন")}</th>
              <th>{t("পণ্য")}</th>
              <th>{t("মূল্য")}</th>
              <th>{t("স্ট্যাটাস")}</th>
              <th>{t("কল")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((order) => (
              <tr key={order.id}>
                <td>
                  <Link to={`/orders/${order.id}`}>{order.order_ref || order.id.slice(0, 8)}</Link>
                </td>
                <td>{order.customer_name}</td>
                <td>{order.customer_phone}</td>
                <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {order.items_summary}
                </td>
                <td>{fmtMoney(order.total_amount)}</td>
                <td>
                  <StatusBadge status={order.status} />
                </td>
                <td className="muted">{t("{n} বার", { n: fmtNum(order.call_attempts) })}</td>
                <td>
                  {["pending", "no_answer", "needs_review"].includes(order.status) && (
                    <button className="btn small" onClick={() => startCall(order.id)}>
                      📞 {t("কল করুন")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <EmptyState
                    art={<BoxArt />}
                    title={t("কোনো অর্ডার নেই")}
                    hint={t("প্রথম অর্ডার যোগ করলেই এআই কল শুরু করা যাবে")}
                    action={
                      <Link to="/orders/new" className="btn small">
                        + {t("নতুন অর্ডার")}
                      </Link>
                    }
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
