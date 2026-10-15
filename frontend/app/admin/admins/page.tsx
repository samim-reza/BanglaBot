"use client";

import { CircleAlert } from "lucide-react";

import { useAdminMe } from "@/components/admin/shell/admin-me";
import { LoadingRows } from "@/components/admin/states";
import { AdminUsersTable } from "@/components/admin/users/admin-users-table";
import { MyAccountCard } from "@/components/admin/users/my-account-card";
import { TwoFactorCard } from "@/components/admin/users/two-factor-card";
import { PageHeader } from "@/components/page-header";

export default function AdminAdminsPage() {
  const { me, loading, can } = useAdminMe();
  const manage = can("manageAdmins");
  if (loading) return <LoadingRows label="Loading…" rows={4} />;
  return (
    <>
      <PageHeader title={manage ? "Admins" : "My account"} />
      {me?.setup_login ? (
        <div className="flex items-start gap-3 rounded-md border border-[#fcd34d] bg-[#fef3c7] p-3 text-sm text-[#92400e] dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>Signed in with the setup login. Create a superadmin below, then sign in as them — the setup login stops working once an admin exists.</p>
        </div>
      ) : (
        me && (
          <div className="grid gap-6 lg:grid-cols-2">
            <MyAccountCard me={me} />
            <TwoFactorCard me={me} />
          </div>
        )
      )}
      {manage && <AdminUsersTable selfId={me?.setup_login ? undefined : me?.id} />}
    </>
  );
}
