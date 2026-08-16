import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { AdminTicket, AdminTicketDetail, Page, TICKET_STATUS_LABELS, TicketStatus } from "../../api/types";
import Pagination from "../../components/Pagination";
import { useLang } from "../../i18n";

const PAGE_SIZE = 10;
const PRIORITY_LABELS: Record<string, string> = { normal: "সাধারণ", urgent: "জরুরি" };

export default function AdminSupport() {
  const { t, fmtDateTime } = useLang();
  const [data, setData] = useState<Page<AdminTicket> | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ticket, setTicket] = useState<AdminTicketDetail | null>(null);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status) params.set("status", status);
    api<Page<AdminTicket>>(`/api/admin/support/tickets?${params}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page, status]);

  useEffect(loadList, [loadList]);

  // Bumped on selection change and every mutation so a slow in-flight poll
  // can't overwrite newer state.
  const version = useRef(0);

  const loadTicket = useCallback(() => {
    if (!selectedId) return;
    const v = version.current;
    api<AdminTicketDetail>(`/api/admin/support/tickets/${selectedId}`)
      .then((res) => {
        if (v === version.current) setTicket(res);
      })
      .catch((e) => setError(e.message));
  }, [selectedId]);

  useEffect(() => {
    version.current += 1;
    setTicket(null);
    loadTicket();
    const timer = setInterval(loadTicket, 10000);
    return () => clearInterval(timer);
  }, [loadTicket]);

  async function sendReply(e: FormEvent) {
    e.preventDefault();
    if (!selectedId || !reply.trim()) return;
    setError("");
    setBusy(true);
    try {
      const res = await api<AdminTicketDetail>(`/api/admin/support/tickets/${selectedId}/messages`, {
        method: "POST",
        body: { body: reply },
      });
      version.current += 1;
      setTicket(res);
      setReply("");
      loadList();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function patchTicket(body: { status?: string; priority?: string }) {
    if (!selectedId) return;
    setError("");
    try {
      const res = await api<AdminTicketDetail>(`/api/admin/support/tickets/${selectedId}`, {
        method: "PATCH",
        body,
      });
      version.current += 1;
      setTicket(res);
      loadList();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <style>{`
        .support-panes { display: grid; grid-template-columns: 1fr 1.4fr; gap: 16px; align-items: start; }
        @media (max-width: 860px) { .support-panes { grid-template-columns: 1fr; } }
      `}</style>
      <h1 className="page-title">{t("সাপোর্ট টিকিট")}</h1>
      {error && <p className="error">{t(error)}</p>}
      <div className="support-panes">
        <div>
          <div className="toolbar">
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{t("সব স্ট্যাটাস")}</option>
              {Object.entries(TICKET_STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {data?.items.map((tk) => (
              <div
                className="card"
                key={tk.id}
                onClick={() => setSelectedId(tk.id)}
                style={{
                  cursor: "pointer",
                  padding: "12px 16px",
                  outline: selectedId === tk.id ? "2px solid #99d5cf" : "none",
                }}
              >
                <p>
                  <b>{tk.reference}</b> — {tk.subject}
                </p>
                <p className="muted" style={{ fontSize: 13.5, margin: "4px 0" }}>
                  {tk.merchant_name}
                </p>
                <p style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  <span className={`badge ${tk.status}`}>
                    {t(TICKET_STATUS_LABELS[tk.status as TicketStatus] ?? tk.status)}
                  </span>
                  <span className={`badge ${tk.priority}`}>{t(PRIORITY_LABELS[tk.priority] ?? tk.priority)}</span>
                  <span className="muted" style={{ fontSize: 12.5 }}>
                    {fmtDateTime(tk.last_message_at)}
                  </span>
                </p>
              </div>
            ))}
            {data && data.items.length === 0 && <p className="muted">{t("কোনো টিকিট নেই")}</p>}
          </div>
          {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />}
        </div>
        <div>
          {!selectedId && <p className="muted">{t("বাম পাশ থেকে একটি টিকিট বাছাই করুন")}</p>}
          {selectedId && !ticket && <p className="muted">{t("লোড হচ্ছে...")}</p>}
          {ticket && (
            <>
              <div className="card" style={{ marginBottom: 16 }}>
                <h2 className="page-title" style={{ fontSize: 17 }}>
                  {ticket.reference} — {ticket.subject}
                </h2>
                <p className="muted" style={{ marginBottom: 12 }}>{ticket.merchant_name}</p>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <div className="form-row">
                    <label>{t("স্ট্যাটাস")}</label>
                    <select value={ticket.status} onChange={(e) => patchTicket({ status: e.target.value })}>
                      {Object.entries(TICKET_STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {t(label)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-row">
                    <label>{t("অগ্রাধিকার")}</label>
                    <select value={ticket.priority} onChange={(e) => patchTicket({ priority: e.target.value })}>
                      {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {t(label)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
              <div className="card" style={{ marginBottom: 16 }}>
                <div className="thread">
                  {ticket.messages.map((m) => (
                    <div className={`msg ${m.author_role === "admin" ? "admin" : ""}`} key={m.id}>
                      <p style={{ marginBottom: 4 }}>
                        <b>{m.author_name}</b>{" "}
                        <span className="muted" style={{ fontSize: 12.5 }}>
                          {fmtDateTime(m.created_at)}
                        </span>
                      </p>
                      <p style={{ whiteSpace: "pre-wrap" }}>{m.body}</p>
                    </div>
                  ))}
                </div>
              </div>
              <form className="card form" style={{ maxWidth: "none" }} onSubmit={sendReply}>
                <div className="form-row">
                  <label>{t("উত্তর লিখুন")}</label>
                  <textarea rows={3} value={reply} onChange={(e) => setReply(e.target.value)} required />
                </div>
                <div>
                  <button className="btn" disabled={busy}>
                    {busy ? t("পাঠানো হচ্ছে...") : t("উত্তর পাঠান")}
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </>
  );
}
