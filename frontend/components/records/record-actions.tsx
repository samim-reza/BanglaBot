"use client";

/** The record page's status picker and delete card. */

import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { statusLabel } from "@/lib/vertical";
import { ORDER_STATUSES, type OrderStatus, type VerticalSpec } from "@/services/api";

export function StatusCard({ status, vertical, busy, onChange }: { status: OrderStatus; vertical: VerticalSpec; busy: boolean; onChange: (status: OrderStatus) => void }) {
  const choices = ORDER_STATUSES.filter((value) => value !== "calling");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Status</CardTitle>
        <CardDescription>Set by your agent; change it anytime.</CardDescription>
      </CardHeader>
      <CardContent>
        <label className="flex flex-col gap-1.5 text-sm sm:max-w-xs">
          <span className="sr-only">Status</span>
          <Select value={status} disabled={busy || status === "calling"} onChange={(event) => onChange(event.target.value as OrderStatus)}>
            {status === "calling" && (
              <option value="calling" disabled>
                {statusLabel(vertical, "calling")}
              </option>
            )}
            {choices.map((value) => (
              <option key={value} value={value}>
                {statusLabel(vertical, value)}
              </option>
            ))}
          </Select>
          {status === "calling" && <span className="text-xs text-muted-foreground">Call in progress.</span>}
        </label>
      </CardContent>
    </Card>
  );
}

export function DeleteCard({ singular, disabled, onDelete }: { singular: string; disabled: boolean; onDelete: () => void }) {
  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle>Delete {singular.toLowerCase()}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">Its calls and chats stay in your log.</p>
        <Button variant="destructive" size="sm" onClick={onDelete} disabled={disabled}>
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          Delete
        </Button>
      </CardContent>
    </Card>
  );
}
