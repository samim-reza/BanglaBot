"use client";

import { Suspense, useCallback, useEffect, useId, useState } from "react";
import { Building2, Globe2, Mail, Phone, PhoneCall, Trash2 } from "lucide-react";

import { INQUIRIES_CHANGED_EVENT } from "@/components/admin-shell";
import { INQUIRY_STATUSES, InquiryStatusBadge } from "@/components/admin/badges";
import { ConfirmDialog } from "@/components/admin/overlay";
import { LoadingRows } from "@/components/admin/states";
import { pageFrom, useUrlFilters } from "@/components/admin/url-filters";
import { useAdminMeta, verticalName } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { adminApi, formatApiError, type AdminMeta, type SalesInquiry, type SalesInquiryStatus } from "@/services/api";

const PAGE_SIZE = 20;
const FILTER_KEYS = ["status", "page"] as const;
const STATUS_VALUES = INQUIRY_STATUSES.map((item) => item.value) as string[];

type Counts = Partial<Record<SalesInquiryStatus | "all", number>>;

export default function AdminInquiriesPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading inquiries…" />}>
      <InquiriesView />
    </Suspense>
  );
}

function notifyNav() {
  window.dispatchEvent(new Event(INQUIRIES_CHANGED_EVENT));
}

function InquiriesView() {
  const toast = useAppToast();
  const { meta } = useAdminMeta();
  const [filters, setFilters] = useUrlFilters(FILTER_KEYS);
  const status = STATUS_VALUES.includes(filters.status) ? (filters.status as SalesInquiryStatus) : "";
  const page = pageFrom(filters.page);

  const [items, setItems] = useState<SalesInquiry[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Counts>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<SalesInquiry | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await adminApi.inquiries({ status, page, page_size: PAGE_SIZE });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setItems([]);
      setTotal(0);
      setError(formatApiError(err, "Could not load sales inquiries."));
    } finally {
      setLoading(false);
    }
  }, [status, page]);

  const loadCounts = useCallback(async () => {
    const keys: (SalesInquiryStatus | "")[] = ["", ...INQUIRY_STATUSES.map((item) => item.value)];
    const results = await Promise.allSettled(keys.map((key) => adminApi.inquiries({ status: key, page_size: 1 })));
    const next: Counts = {};
    results.forEach((result, index) => {
      if (result.status === "fulfilled") next[(keys[index] || "all") as SalesInquiryStatus | "all"] = result.value.total;
    });
    setCounts(next);
  }, []);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    void loadCounts();
  }, [loadCounts]);

  const replace = (updated: SalesInquiry) => setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));

  const tabs: { value: SalesInquiryStatus | ""; label: string }[] = [{ value: "", label: "All" }, ...INQUIRY_STATUSES];

  return (
    <>
      <PageHeader title="Sales inquiries" subtitle="Leads from the website's “Talk to sales” form. Track each one from first reply to won or lost." />
      <ApiError message={error} />

      <div role="group" aria-label="Filter by status" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
        {tabs.map((tab) => {
          const active = status === tab.value;
          const count = counts[(tab.value || "all") as SalesInquiryStatus | "all"];
          return (
            <button
              key={tab.value || "all"}
              type="button"
              aria-pressed={active}
              onClick={() => setFilters({ status: tab.value, page: null })}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active ? "border-primary bg-accent text-accent-foreground" : "border-border bg-card text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              {tab.label}
              {count !== undefined && (
                <span className={cn("rounded-full px-1.5 text-xs tabular-nums", active ? "bg-primary text-primary-foreground" : "bg-secondary")}>{count}</span>
              )}
            </button>
          );
        })}
      </div>

      {loading && items.length === 0 ? (
        <LoadingRows label="Loading inquiries…" rows={4} />
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={status ? "No inquiries with this status" : "No inquiries yet"}>
            {status ? "Pick another status above." : "When someone sends the website's Talk to sales form, it lands here."}
          </EmptyState>
        )
      ) : (
        <ul className="space-y-4" aria-busy={loading}>
          {items.map((inquiry) => (
            <li key={inquiry.id}>
              <InquiryCard
                inquiry={inquiry}
                meta={meta}
                onUpdated={(updated, statusChanged) => {
                  replace(updated);
                  if (statusChanged) {
                    void loadCounts();
                    notifyNav();
                  }
                }}
                onDelete={() => setDeleting(inquiry)}
                onError={(message) => toast.error(message)}
              />
            </li>
          ))}
        </ul>
      )}

      {total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={(next) => setFilters({ page: next })} />}

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        title="Delete inquiry?"
        tone="danger"
        confirmLabel="Delete inquiry"
        busyLabel="Deleting…"
        onConfirm={async () => {
          if (!deleting) return;
          await adminApi.deleteInquiry(deleting.id);
          toast.success("Inquiry deleted.");
          setDeleting(null);
          notifyNav();
          void loadCounts();
          // Step back a page when the last item on this page goes.
          if (items.length === 1 && page > 1) setFilters({ page: page - 1 });
          else void load();
        }}
      >
        <p>
          This removes the inquiry from <strong className="text-foreground">{deleting?.name}</strong>
          {deleting?.company ? ` (${deleting.company})` : ""} and your notes on it. It can&apos;t be undone.
        </p>
      </ConfirmDialog>
    </>
  );
}

function InquiryCard({
  inquiry,
  meta,
  onUpdated,
  onDelete,
  onError,
}: {
  inquiry: SalesInquiry;
  meta: AdminMeta | null;
  onUpdated: (inquiry: SalesInquiry, statusChanged: boolean) => void;
  onDelete: () => void;
  onError: (message: string) => void;
}) {
  const toast = useAppToast();
  const notesId = useId();
  const statusId = useId();
  const [notes, setNotes] = useState(inquiry.admin_notes ?? "");
  const [savingNotes, setSavingNotes] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);

  useEffect(() => {
    setNotes(inquiry.admin_notes ?? "");
  }, [inquiry.id, inquiry.admin_notes]);

  const dirty = notes !== (inquiry.admin_notes ?? "");
  const businessType = inquiry.business_type
    ? meta?.verticals.some((spec) => spec.key === inquiry.business_type)
      ? verticalName(meta, inquiry.business_type)
      : inquiry.business_type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
    : "";

  const changeStatus = async (next: SalesInquiryStatus) => {
    if (next === inquiry.status) return;
    setSavingStatus(true);
    try {
      const updated = await adminApi.updateInquiry(inquiry.id, { status: next });
      onUpdated(updated, true);
      toast.success(`Marked as ${INQUIRY_STATUSES.find((item) => item.value === next)?.label.toLowerCase() ?? next}.`);
    } catch (err) {
      onError(formatApiError(err, "Could not update the status."));
    } finally {
      setSavingStatus(false);
    }
  };

  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      const updated = await adminApi.updateInquiry(inquiry.id, { admin_notes: notes });
      onUpdated(updated, false);
      toast.success("Notes saved.");
    } catch (err) {
      onError(formatApiError(err, "Could not save the notes."));
    } finally {
      setSavingNotes(false);
    }
  };

  return (
    <article className="rounded-lg border border-border bg-card p-4 sm:p-5" aria-labelledby={`${notesId}-title`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={`${notesId}-title`} className="text-base font-semibold">
              {inquiry.name}
            </h2>
            <InquiryStatusBadge status={inquiry.status} />
          </div>
          <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {inquiry.company && (
              <div>
                <dt className="sr-only">Company</dt>
                <dd className="inline-flex items-center gap-1.5 text-foreground">
                  <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {inquiry.company}
                </dd>
              </div>
            )}
            {businessType && (
              <div>
                <dt className="sr-only">Business type</dt>
                <dd>{businessType}</dd>
              </div>
            )}
            {inquiry.country && (
              <div>
                <dt className="sr-only">Country</dt>
                <dd className="inline-flex items-center gap-1.5">
                  <Globe2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {inquiry.country}
                </dd>
              </div>
            )}
            {inquiry.monthly_calls && (
              <div>
                <dt className="sr-only">Monthly calls</dt>
                <dd className="inline-flex items-center gap-1.5">
                  <PhoneCall className="h-3.5 w-3.5" aria-hidden="true" />
                  {inquiry.monthly_calls} calls / month
                </dd>
              </div>
            )}
          </dl>
        </div>
        <time className="shrink-0 text-xs text-muted-foreground" dateTime={inquiry.created_at}>
          {formatDateTime(inquiry.created_at)}
        </time>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {inquiry.email && (
          <a
            href={`mailto:${inquiry.email}`}
            className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm font-medium text-primary hover:bg-secondary"
          >
            <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">{inquiry.email}</span>
          </a>
        )}
        {inquiry.phone && (
          <a
            href={`tel:${inquiry.phone}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm font-medium text-primary hover:bg-secondary"
          >
            <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {inquiry.phone}
          </a>
        )}
      </div>

      {inquiry.message ? (
        <blockquote className="mt-3 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-md border-l-4 border-tint-strong bg-surface px-3 py-2 text-sm">
          {inquiry.message}
        </blockquote>
      ) : (
        <p className="mt-3 text-sm italic text-muted-foreground">No message.</p>
      )}

      <div className="mt-4 grid gap-3 border-t border-border pt-4 md:grid-cols-[12rem_1fr]">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={statusId} className="text-[13.5px] font-semibold text-muted-foreground">
            Status
          </label>
          <Select
            id={statusId}
            value={inquiry.status}
            disabled={savingStatus}
            onChange={(event) => void changeStatus(event.target.value as SalesInquiryStatus)}
          >
            {INQUIRY_STATUSES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={notesId} className="text-[13.5px] font-semibold text-muted-foreground">
            Internal notes
          </label>
          <Textarea
            id={notesId}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={2}
            maxLength={4000}
            placeholder="Call outcome, next step, who owns the follow-up…"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={onDelete}
              aria-label={`Delete inquiry from ${inquiry.name}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
            <div className="flex items-center gap-2">
              {dirty && (
                <Button variant="ghost" size="sm" onClick={() => setNotes(inquiry.admin_notes ?? "")} disabled={savingNotes}>
                  Discard
                </Button>
              )}
              <Button size="sm" onClick={() => void saveNotes()} disabled={!dirty || savingNotes}>
                {savingNotes ? "Saving…" : "Save notes"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
