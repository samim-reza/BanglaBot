import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { AuditLog, Page } from "../../api/types";
import MerchantSelect from "../../components/MerchantSelect";
import Pagination from "../../components/Pagination";
import { useLang } from "../../i18n";

const PAGE_SIZE = 30;
const ROLE_LABELS: Record<string, string> = {
  admin: "অ্যাডমিন",
  merchant: "মার্চেন্ট",
  system: "সিস্টেম",
};
const ROLE_BADGE: Record<string, string> = {
  admin: "open",
  merchant: "active",
  system: "normal",
};

export default function AdminLogs() {
  const { t, fmtDateTime } = useLang();
  const [data, setData] = useState<Page<AuditLog> | null>(null);
  const [page, setPage] = useState(1);
  const [actorRole, setActorRole] = useState("");
  const [action, setAction] = useState("");
  const [merchantId, setMerchantId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (actorRole) params.set("actor_role", actorRole);
    if (action) params.set("action", action);
    if (merchantId) params.set("merchant_id", merchantId);
    api<Page<AuditLog>>(`/api/admin/logs?${params}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page, actorRole, action, merchantId]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 20000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <>
      <h1 className="page-title">{t("অডিট লগ")}</h1>
      {error && <p className="error">{t(error)}</p>}
      <div className="toolbar">
        <MerchantSelect
          value={merchantId}
          onChange={(id) => {
            setMerchantId(id);
            setPage(1);
          }}
        />
        <select
          value={actorRole}
          onChange={(e) => {
            setActorRole(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("সব")}</option>
          {Object.entries(ROLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {t(label)}
            </option>
          ))}
        </select>
        <input
          placeholder={t("কাজ (action) দিয়ে খুঁজুন")}
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          style={{ width: 240 }}
        />
      </div>
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("সময়")}</th>
              <th>{t("কে")}</th>
              <th>{t("কাজ")}</th>
              <th>{t("বিবরণ")}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((log) => (
              <tr key={log.id}>
                <td className="muted">{fmtDateTime(log.created_at)}</td>
                <td>
                  {log.actor_name || "—"}{" "}
                  <span className={`badge ${ROLE_BADGE[log.actor_role] ?? "normal"}`}>
                    {t(ROLE_LABELS[log.actor_role] ?? log.actor_role)}
                  </span>
                </td>
                <td className="muted">{log.action}</td>
                <td style={{ whiteSpace: "normal" }}>{log.detail ? t(log.detail) : "—"}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={4} className="muted" style={{ textAlign: "center", padding: 30 }}>
                  {t("কোনো লগ নেই")}
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
