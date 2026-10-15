"use client";

import { useState } from "react";
import { Pencil, ShieldCheck, Trash2, UserPlus } from "lucide-react";

import { ActiveBadge } from "@/components/admin/badges";
import { ConfirmDialog } from "@/components/admin/overlay";
import { LoadingRows } from "@/components/admin/states";
import { useCursorList } from "@/components/admin/use-cursor-list";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { LoadMore } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatDateTime } from "@/lib/format";
import { adminUsersApi, type AdminUser } from "@/services/api/admin/users";

import { AdminUserDialog } from "./admin-user-dialog";
import { RolePill } from "./role-pill";

/** Every console admin (superadmin): create, edit, delete. */
export function AdminUsersTable({ selfId }: { selfId: string | undefined }) {
  const toast = useAppToast();
  const list = useCursorList((cursor) => adminUsersApi.list({ cursor, limit: 50 }), "admins", "Could not load admins.");
  const [editing, setEditing] = useState<AdminUser | null | "new">(null);
  const [deleting, setDeleting] = useState<AdminUser | null>(null);

  const saved = (user: AdminUser, created: boolean) => {
    setEditing(null);
    list.setItems((items) => (created ? [...items, user] : items.map((u) => (u.id === user.id ? user : u))));
    toast.success(created ? `${user.username} created.` : "Saved.");
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Admins</CardTitle>
        <Button size="sm" onClick={() => setEditing("new")}>
          <UserPlus className="h-3.5 w-3.5" />
          New admin
        </Button>
      </CardHeader>
      {list.error && (
        <div className="px-5 pb-4">
          <ApiError message={list.error} />
        </div>
      )}
      {list.loading && list.items.length === 0 ? (
        <LoadingRows label="Loading admins…" rows={3} className="rounded-none border-x-0 border-b-0" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last sign-in</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-24">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.items.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-medium">
                  <span className="inline-flex items-center gap-1.5">
                    {user.username}
                    {user.totp_enabled && <ShieldCheck className="h-3.5 w-3.5 text-primary" aria-label="Two-factor on" />}
                    {user.id === selfId && <span className="text-xs text-muted-foreground">(you)</span>}
                  </span>
                </TableCell>
                <TableCell>
                  <RolePill role={user.role} />
                </TableCell>
                <TableCell>
                  <ActiveBadge active={user.active} />
                </TableCell>
                <TableCell className="whitespace-nowrap">{formatDateTime(user.last_login_at)}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDate(user.created_at)}</TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Edit ${user.username}`} onClick={() => setEditing(user)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive"
                    aria-label={`Delete ${user.username}`}
                    disabled={user.id === selfId}
                    onClick={() => setDeleting(user)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {list.hasMore && (
        <div className="border-t border-border p-3">
          <LoadMore shown={list.items.length} hasMore={list.hasMore} loading={list.loadingMore} onLoadMore={() => void list.loadMore()} noun="admins" />
        </div>
      )}
      <AdminUserDialog open={editing !== null} user={editing === "new" ? null : editing} selfId={selfId} onClose={() => setEditing(null)} onSaved={saved} />
      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        title={`Delete ${deleting?.username ?? "admin"}?`}
        confirmLabel="Delete"
        busyLabel="Deleting…"
        tone="danger"
        confirmText={deleting?.username}
        onConfirm={async () => {
          if (!deleting) return;
          await adminUsersApi.remove(deleting.id);
          list.setItems((items) => items.filter((u) => u.id !== deleting.id));
          setDeleting(null);
          toast.success("Admin deleted.");
        }}
      >
        <p>They are signed out and can&apos;t sign in again. Their audit history stays.</p>
      </ConfirmDialog>
    </Card>
  );
}
