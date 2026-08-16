import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Billing from "./pages/Billing";
import Dashboard from "./pages/Dashboard";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NewOrder from "./pages/NewOrder";
import OrderDetail from "./pages/OrderDetail";
import Orders from "./pages/Orders";
import Settings from "./pages/Settings";
import Signup from "./pages/Signup";
import Support from "./pages/Support";
import SupportTicket from "./pages/SupportTicket";
import AdminBilling from "./pages/admin/AdminBilling";
import AdminCalls from "./pages/admin/AdminCalls";
import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminFinance from "./pages/admin/AdminFinance";
import AdminLogs from "./pages/admin/AdminLogs";
import AdminMerchants from "./pages/admin/AdminMerchants";
import AdminOrders from "./pages/admin/AdminOrders";
import AdminPlans from "./pages/admin/AdminPlans";
import AdminSettings from "./pages/admin/AdminSettings";
import AdminSupport from "./pages/admin/AdminSupport";
import AdminTeam from "./pages/admin/AdminTeam";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route element={<Layout role="merchant" />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/orders/new" element={<NewOrder />} />
          <Route path="/orders/:id" element={<OrderDetail />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/support" element={<Support />} />
          <Route path="/support/:id" element={<SupportTicket />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route element={<Layout role="admin" />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/merchants" element={<AdminMerchants />} />
          <Route path="/admin/orders" element={<AdminOrders />} />
          <Route path="/admin/calls" element={<AdminCalls />} />
          <Route path="/admin/plans" element={<AdminPlans />} />
          <Route path="/admin/billing" element={<AdminBilling />} />
          <Route path="/admin/finance" element={<AdminFinance />} />
          <Route path="/admin/support" element={<AdminSupport />} />
          <Route path="/admin/team" element={<AdminTeam />} />
          <Route path="/admin/logs" element={<AdminLogs />} />
          <Route path="/admin/settings" element={<AdminSettings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
