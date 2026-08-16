import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Page, Ticket, TicketDetail, TICKET_STATUS_LABELS } from "../api/types";
import EmptyState from "../components/EmptyState";
import Pagination from "../components/Pagination";
import { TicketsArt } from "../components/art";
import { useLang } from "../i18n";

const PAGE_SIZE = 10;

export default function Support() {
  const { t, fmtDateTime } = useLang();
  const [data, setData] = useState<Page<Ticket> | null>(null);
  const [page, setPage] = useState(1);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState("normal");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(() => {
    api<Page<Ticket>>(`/api/support/tickets?page=${page}&page_size=${PAGE_SIZE}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const ticket = await api<TicketDetail>("/api/support/tickets", {
        method: "POST",
        body: { subject, message, priority },
      });
      navigate(`/support/${ticket.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="page-title">{t("সাপোর্ট")}</h1>
      <form className="card form" style={{ marginBottom: 16 }} onSubmit={submit}>
        <h2 className="page-title" style={{ fontSize: 17, marginBottom: 0 }}>
          {t("নতুন টিকিট")}
        </h2>
        <div className="form-row">
          <label>{t("বিষয় *")}</label>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} minLength={3} required />
        </div>
        <div className="form-row">
          <label>{t("বার্তা *")}</label>
          <textarea
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            minLength={3}
            required
          />
        </div>
        <div className="form-row">
          <label>{t("অগ্রাধিকার")}</label>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="normal">{t("সাধারণ")}</option>
            <option value="urgent">{t("জরুরি")}</option>
          </select>
        </div>
        {error && <div className="error">{t(error)}</div>}
        <div>
          <button className="btn" disabled={busy}>
            {busy ? t("পাঠানো হচ্ছে...") : t("টিকিট খুলুন")}
          </button>
        </div>
      </form>

      <h2 className="page-title" style={{ fontSize: 17 }}>
        {t("আমার টিকিট")}
      </h2>
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("রেফারেন্স")}</th>
              <th>{t("বিষয়")}</th>
              <th>{t("স্ট্যাটাস")}</th>
              <th>{t("শেষ বার্তা")}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((tk) => (
              <tr key={tk.id}>
                <td>
                  <Link to={`/support/${tk.id}`}>{tk.reference}</Link>
                </td>
                <td>{tk.subject}</td>
                <td>
                  <span className={`badge ${tk.status}`}>{t(TICKET_STATUS_LABELS[tk.status])}</span>
                </td>
                <td className="muted">{fmtDateTime(tk.last_message_at)}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <EmptyState
                    art={<TicketsArt />}
                    title={t("কোনো টিকিট নেই")}
                    hint={t("প্রশ্ন থাকলে উপরের ফর্ম থেকে টিকিট খুলুন")}
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
