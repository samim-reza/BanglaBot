import { AdminGate, AdminShell } from "@/components/admin-shell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminShell>
      <AdminGate>{children}</AdminGate>
    </AdminShell>
  );
}
