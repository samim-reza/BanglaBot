import { FormEvent, Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { Order, OrderStatus, Page, STATUS_LABELS } from "../../api/types";
import EmptyState from "../../components/EmptyState";
import MerchantSelect from "../../components/MerchantSelect";
import Pagination from "../../components/Pagination";
import { BoxArt } from "../../components/art";
import StatusBadge from "../../components/StatusBadge";
import { useLang } from "../../i18n";

const PAGE_SIZE = 20;

interface OrderEditForm {
  order_ref: string;
  customer_name: string;
  customer_phone: string;
  items_summary: string;
  total_amount: string;
  notes: string;
  status: OrderStatus;
}

export default function AdminOrders() {
  const { t, fmtNum, fmtMoney, fmtDate } = useLang();
  const [data, setData] = useState<Page<Order> | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [merchantId, setMerchantId] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [editFor, setEditFor] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<OrderEditForm | null>(null);
  const [editBusy, setEditBusy] = useState(false);

  const load = useCallback((isStale?: () => boolean) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status) params.set("status", status);
    if (merchantId) params.set("merchant_id", merchantId);
    if (search) params.set("search", search);
    api<Page<Order>>(`/api/admin/orders?${params}`)
      .then((d) => {
        if (!isStale?.()) setData(d);
      })
      .catch(() => {});
  }, [page, status, merchantId, search]);

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

  function openEditor(order: Order) {
    if (editFor === order.id) {
      setEditFor(null);
      return;
    }
    setEditFor(order.id);
    setEditForm({
      order_ref: order.order_ref,
      customer_name: order.customer_name,
      customer_phone: order.customer_phone,
      items_summary: order.items_summary,
      total_amount: String(order.total_amount),
      notes: order.notes,
      status: order.status,
    });
  }

  const setEdit = (key: keyof OrderEditForm) => (e: { target: { value: string } }) =>
    setEditForm((f) => (f ? { ...f, [key]: e.target.value } : f));

  async function saveEdit(e: FormEvent, order: Order) {
    e.preventDefault();
    if (!editForm) return;
    setError("");
    setEditBusy(true);
    try {
      await api(`/api/admin/orders/${order.id}`, {
        method: "PATCH",
        body: { ...editForm, total_amount: Number(editForm.total_amount || 0) },
      });
      setEditFor(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEditBusy(false);
    }
  }

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
        <MerchantSelect
          value={merchantId}
          onChange={(id) => {
            setMerchantId(id);
            setPage(1);
          }}
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
      {error && <p className="error">{t(error)}</p>}
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
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((order) => (
              <Fragment key={order.id}>
                <tr>
                  <td>{order.order_ref || order.id.slice(0, 8)}</td>
                  <td>{order.customer_name}</td>
                  <td>{order.customer_phone}</td>
                  <td>{fmtMoney(order.total_amount)}</td>
                  <td>
                    <StatusBadge status={order.status} />
                  </td>
                  <td className="muted">{t("{n} বার", { n: fmtNum(order.call_attempts) })}</td>
                  <td className="muted">{fmtDate(order.created_at)}</td>
                  <td>
                    <button className="btn secondary small" onClick={() => openEditor(order)}>
                      ✏️ {t("সম্পাদনা")}
                    </button>
                  </td>
                </tr>
                {editFor === order.id && editForm && (
                  <tr>
                    <td colSpan={8} style={{ background: "#fafbfc" }}>
                      <form
                        className="form"
                        style={{ maxWidth: "none", padding: "8px 0" }}
                        onSubmit={(e) => saveEdit(e, order)}
                      >
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
                          <div className="form-row">
                            <label>{t("অর্ডার নম্বর (ঐচ্ছিক)")}</label>
                            <input
                              value={editForm.order_ref}
                              onChange={setEdit("order_ref")}
                              style={{ width: 120 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("কাস্টমারের নাম *")}</label>
                            <input
                              value={editForm.customer_name}
                              onChange={setEdit("customer_name")}
                              required
                              style={{ width: 150 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("ফোন নম্বর *")}</label>
                            <input
                              value={editForm.customer_phone}
                              onChange={setEdit("customer_phone")}
                              required
                              style={{ width: 140 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("পণ্যের বিবরণ")}</label>
                            <input
                              value={editForm.items_summary}
                              onChange={setEdit("items_summary")}
                              style={{ width: 180 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("মোট মূল্য (টাকা)")}</label>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={editForm.total_amount}
                              onChange={setEdit("total_amount")}
                              style={{ width: 110 }}
                            />
                          </div>
                          <div className="form-row">
                            <label>{t("স্ট্যাটাস")}</label>
                            <select
                              value={editForm.status}
                              onChange={setEdit("status")}
                              style={{ width: 150 }}
                            >
                              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>
                                  {t(label)}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-row" style={{ flex: 1, minWidth: 160 }}>
                            <label>{t("নোট")}</label>
                            <input value={editForm.notes} onChange={setEdit("notes")} />
                          </div>
                          <button className="btn small" disabled={editBusy}>
                            {editBusy ? t("সংরক্ষণ হচ্ছে...") : t("সংরক্ষণ")}
                          </button>
                        </div>
                      </form>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={8}>
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
