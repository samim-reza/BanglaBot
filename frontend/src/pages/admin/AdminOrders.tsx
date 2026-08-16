import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { Order, Page, STATUS_LABELS } from "../../api/types";
import EmptyState from "../../components/EmptyState";
import Pagination from "../../components/Pagination";
import { BoxArt } from "../../components/art";
import StatusBadge from "../../components/StatusBadge";
import { useLang } from "../../i18n";

const PAGE_SIZE = 20;

export default function AdminOrders() {
  const { t, fmtNum, fmtMoney, fmtDate } = useLang();
  const [data, setData] = useState<Page<Order> | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback((isStale?: () => boolean) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    api<Page<Order>>(`/api/admin/orders?${params}`)
      .then((d) => {
        if (!isStale?.()) setData(d);
      })
      .catch(() => {});
  }, [page, status, search]);

  useEffect(() => {
    // Filters retrigger this effect; the stale flag drops slow out-of-date responses.
    let stale = false;
    const run = () => load(() => stale);
    run();
    const timer = setInterval(run, 10000);
    return () => {
      stale = true;
      clearInterval(timer);
    };
  }, [load]);

  return (
    <>
      <h1 className="page-title">{t("সব অর্ডার")}</h1>
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
      </div>
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("অর্ডার")}</th>
              <th>{t("কাস্টমার")}</th>
              <th>{t("ফোন")}</th>
              <th>{t("মূল্য")}</th>
              <th>{t("স্ট্যাটাস")}</th>
              <th>{t("কল")}</th>
              <th>{t("তারিখ")}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((order) => (
              <tr key={order.id}>
                <td>{order.order_ref || order.id.slice(0, 8)}</td>
                <td>{order.customer_name}</td>
                <td>{order.customer_phone}</td>
                <td>{fmtMoney(order.total_amount)}</td>
                <td>
                  <StatusBadge status={order.status} />
                </td>
                <td className="muted">{t("{n} বার", { n: fmtNum(order.call_attempts) })}</td>
                <td className="muted">{fmtDate(order.created_at)}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState art={<BoxArt />} title={t("কোনো অর্ডার নেই")} />
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
