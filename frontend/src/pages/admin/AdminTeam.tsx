import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useLang } from "../../i18n";

// টাইপটি types.ts-এ নেই বলে এখানে সংজ্ঞায়িত (AdminUserOut)
interface AdminUser {
  id: string;
  username: string;
  name: string;
  created_at: string;
}

const EMPTY = { username: "", name: "", password: "" };

export default function AdminTeam() {
  const { t, fmtDate } = useLang();
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<AdminUser[]>("/api/admin/team").then(setAdmins).catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const set = (key: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/admin/team", { method: "POST", body: form });
      setForm(EMPTY);
      setShowForm(false);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function resetPassword(admin: AdminUser) {
    const password = prompt(t('"{username}"-এর নতুন পাসওয়ার্ড:', { username: admin.username }));
    if (!password) return;
    setError("");
    try {
      await api(`/api/admin/team/${admin.id}`, { method: "PATCH", body: { password } });
      alert(t("পাসওয়ার্ড পরিবর্তন হয়েছে"));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(admin: AdminUser) {
    if (!window.confirm(t('"{username}" অ্যাডমিন মুছে ফেলতে চান?', { username: admin.username }))) return;
    setError("");
    try {
      await api(`/api/admin/team/${admin.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>{t("অ্যাডমিন টিম")}</h1>
        <span className="spacer" />
        <button className="btn" onClick={() => setShowForm((s) => !s)}>
          {showForm ? t("বন্ধ করুন") : t("+ নতুন অ্যাডমিন")}
        </button>
      </div>
      {error && <p className="error">{t(error)}</p>}
      {showForm && (
        <form className="card form" style={{ marginBottom: 16 }} onSubmit={submit}>
          <div className="form-row">
            <label>{t("ইউজারনেম *")}</label>
            <input value={form.username} onChange={set("username")} required />
          </div>
          <div className="form-row">
            <label>{t("নাম *")}</label>
            <input value={form.name} onChange={set("name")} required />
          </div>
          <div className="form-row">
            <label>{t("পাসওয়ার্ড *")}</label>
            <input value={form.password} onChange={set("password")} required />
          </div>
          <button className="btn">{t("তৈরি করুন")}</button>
        </form>
      )}
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("ইউজারনেম")}</th>
              <th>{t("নাম")}</th>
              <th>{t("যোগ হয়েছে")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {admins.map((admin) => (
              <tr key={admin.id}>
                <td>{admin.username}</td>
                <td>{admin.name}</td>
                <td className="muted">{fmtDate(admin.created_at)}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  <button className="btn secondary small" onClick={() => resetPassword(admin)}>
                    {t("পাসওয়ার্ড রিসেট")}
                  </button>
                  <button className="btn danger small" onClick={() => remove(admin)}>
                    {t("মুছুন")}
                  </button>
                </td>
              </tr>
            ))}
            {admins.length === 0 && (
              <tr>
                <td colSpan={4} className="muted" style={{ textAlign: "center", padding: 30 }}>
                  {t("কোনো অ্যাডমিন নেই")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
