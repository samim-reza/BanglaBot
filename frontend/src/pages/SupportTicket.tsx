import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { TicketDetail, TICKET_STATUS_LABELS } from "../api/types";
import { useLang } from "../i18n";

export default function SupportTicket() {
  const { t, fmtDateTime } = useLang();
  const { id } = useParams();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Bumped on every mutation so a slow in-flight poll can't overwrite newer state.
  const version = useRef(0);

  const load = useCallback(() => {
    const v = version.current;
    api<TicketDetail>(`/api/support/tickets/${id}`)
      .then((res) => {
        if (v === version.current) setTicket(res);
      })
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!reply.trim()) return;
    setError("");
    setBusy(true);
    try {
      const res = await api<TicketDetail>(`/api/support/tickets/${id}/messages`, {
        method: "POST",
        body: { body: reply },
      });
      version.current += 1;
      setTicket(res);
      setReply("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!ticket) return <p className="muted">{error ? t(error) : t("লোড হচ্ছে...")}</p>;

  return (
    <>
      <p style={{ marginBottom: 10 }}>
        <Link to="/support">← {t("সব টিকিট")}</Link>
      </p>
      <h1 className="page-title">
        {ticket.reference} — {ticket.subject}{" "}
        <span className={`badge ${ticket.status}`}>{t(TICKET_STATUS_LABELS[ticket.status])}</span>
      </h1>
      {error && <p className="error">{t(error)}</p>}
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
      <form className="card form" style={{ maxWidth: "none" }} onSubmit={submit}>
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
  );
}
