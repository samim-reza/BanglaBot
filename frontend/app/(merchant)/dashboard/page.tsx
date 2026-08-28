"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, ClipboardList, PhoneCall, PhoneMissed, PlusCircle, XCircle } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader, StatTile } from "@/components/page-header";
import { OrderStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatMoney } from "@/lib/format";
import { formatApiError, getMerchantSession, ordersApi, type Order, type OrderStats } from "@/services/api";

export default function DashboardPage() {
  const [stats, setStats] = useState<OrderStats | null>(null);
  const [recent, setRecent] = useState<Order[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [businessName, setBusinessName] = useState("");

  const load = useCallback(async () => {
    try {
      const [nextStats, page] = await Promise.all([ordersApi.stats(), ordersApi.list({ page: 1, page_size: 8 })]);
      setStats(nextStats);
      setRecent(page.items);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load the dashboard."));
    }
  }, []);

  useEffect(() => {
    setBusinessName(getMerchantSession().merchant?.business_name ?? "");
    void load();
  }, [load]);

  // Keep the tiles fresh while calls are in flight.
  useEffect(() => {
    if (!stats?.calling) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [stats?.calling, load]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={businessName ? `${businessName}` : "Dashboard"}
        subtitle="Orders waiting for confirmation and what the agent has settled today."
        actions={
          <Button asChild>
            <Link href="/orders/new">
              <PlusCircle className="h-4 w-4" />
              New order
            </Link>
          </Button>
        }
      />
      <ApiError message={error} />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Pending" value={stats?.pending ?? "—"} icon={ClipboardList} hint="Waiting for a call" />
        <StatTile label="Calling" value={stats?.calling ?? "—"} icon={PhoneCall} accent="text-[#1d4ed8] dark:text-blue-300" hint="Agent on the line" />
        <StatTile label="Confirmed" value={stats?.confirmed ?? "—"} icon={CheckCircle2} accent="text-[#065f46] dark:text-emerald-300" hint="Ready to ship" />
        <StatTile label="Cancelled" value={stats?.cancelled ?? "—"} icon={XCircle} accent="text-destructive" hint="Customer declined" />
        <StatTile label="No answer" value={stats?.no_answer ?? "—"} icon={PhoneMissed} accent="text-[#5b21b6] dark:text-violet-300" hint="Try again later" />
        <StatTile label="Needs review" value={stats?.needs_review ?? "—"} icon={AlertTriangle} accent="text-[#9a3412] dark:text-orange-300" hint="Check the transcript" />
        <StatTile label="Total orders" value={stats?.total ?? "—"} hint="All time" />
      </section>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Recent orders</CardTitle>
          <Button asChild variant="outline" size="sm">
            <Link href="/orders">View all</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {recent.length === 0 ? (
            <EmptyState title="No orders yet">
              Add your first order and BanglaBot will call the customer to confirm it.
            </EmptyState>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Items</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell>
                      <Link href={`/orders/${order.id}`} className="font-medium hover:underline">
                        {order.customer_name}
                      </Link>
                      <div className="text-xs text-muted-foreground">{order.customer_phone}</div>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground">{order.items_summary || "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(order.total_amount, order.currency)}</TableCell>
                    <TableCell>
                      <OrderStatusBadge status={order.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(order.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
