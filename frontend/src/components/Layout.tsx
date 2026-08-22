import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { auth } from "../api/client";
import { LangToggle, useLang } from "../i18n";
import { clearServiceCache, serviceText, useServiceType } from "../service";

export default function Layout({ role }: { role: "merchant" | "admin" }) {
  const navigate = useNavigate();
  const { t } = useLang();
  const service = useServiceType(role === "merchant" && auth.role === "merchant");
  if (!auth.token) return <Navigate to="/login" replace />;
  if (auth.role !== role)
    return <Navigate to={auth.role === "admin" ? "/admin" : "/dashboard"} replace />;

  const links =
    role === "merchant"
      ? [
          { to: "/dashboard", label: "ড্যাশবোর্ড" },
          { to: "/orders", label: serviceText(service).navOrders },
          { to: "/billing", label: "বিলিং" },
          { to: "/support", label: "সাপোর্ট" },
          { to: "/settings", label: "সেটিংস" },
        ]
      : [
          { to: "/admin", label: "ড্যাশবোর্ড" },
          { to: "/admin/merchants", label: "মার্চেন্ট" },
          { to: "/admin/orders", label: "অর্ডার" },
          { to: "/admin/calls", label: "কল" },
          { to: "/admin/plans", label: "প্ল্যান" },
          { to: "/admin/billing", label: "বিলিং" },
          { to: "/admin/finance", label: "ফাইন্যান্স" },
          { to: "/admin/support", label: "সাপোর্ট" },
          { to: "/admin/team", label: "টিম" },
          { to: "/admin/logs", label: "লগ" },
          { to: "/admin/settings", label: "সেটিংস" },
        ];

  return (
    <>
      <header className="topbar">
        <span className="brand">📞 BanglaBot</span>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === "/dashboard" || l.to === "/admin"}>
              {t(l.label)}
            </NavLink>
          ))}
        </nav>
        <LangToggle />
        <span className="user">{auth.name}</span>
        <button
          className="btn secondary small"
          onClick={() => {
            auth.clear();
            clearServiceCache();
            navigate("/login");
          }}
        >
          {t("লগআউট")}
        </button>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}
