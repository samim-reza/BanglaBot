"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  ClipboardList,
  Globe,
  Lock,
  LogIn,
  MessageCircle,
  MessagesSquare,
  Pencil,
  PhoneIncoming,
  Trash2,
  Webhook,
} from "lucide-react";

import { ActiveBadge, Pill } from "@/components/admin/badges";
import { DeleteMerchantDialog, OpenPortalDialog } from "@/components/admin/merchant-actions";
import { MerchantEditDrawer } from "@/components/admin/merchant-edit-drawer";
import { PlanAddonsCard } from "@/components/admin/plan-addons-card";
import { LoadingRows } from "@/components/admin/states";
import { Meter } from "@/components/admin/stats";
import { planPrice, regionOf, useAddonCatalog, useAdminMeta, verticalOf } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { EmptyState } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatDateTime, languageLabel } from "@/lib/format";
import { t } from "@/lib/vertical";
import { adminApi, formatApiError, isApiRequestError, type AdminMerchantDetail, type ChannelKey } from "@/services/api";

const num = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 1 });

export default function AdminAccountDetailPage() {
  const params = useParams<{ id: string }>();
  const id = String(params?.id ?? "");
  const router = useRouter();
  const { meta } = useAdminMeta();
  const { addons: catalog, error: catalogError } = useAddonCatalog();
  const [detail, setDetail] = useState<AdminMerchantDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [opening, setOpening] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setDetail(await adminApi.merchant(id));
      setError(null);
      setNotFound(false);
    } catch (err) {
      if (isApiRequestError(err) && err.status === 404) setNotFound(true);
      else setError(formatApiError(err, "Could not load this account."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const backLink = (
    <Link href="/admin/merchants" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Accounts
    </Link>
  );

  if (loading) {
    return (
      <>
        {backLink}
        <LoadingRows label="Loading account…" rows={6} />
      </>
    );
  }

  if (notFound || !detail) {
    return (
      <>
        {backLink}
        <ApiError message={error} />
        {notFound && <EmptyState title="Account not found">It may have been deleted.</EmptyState>}
      </>
    );
  }

  const { merchant, usage } = detail;
  const spec = verticalOf(meta, merchant.vertical);
  const region = regionOf(meta, merchant.region);
  const plan = usage.plan;
  const recordsLabel = spec ? t(spec.record_label_plural, "Records") : "Records";
  const catalogLabel = spec ? t(spec.catalog_label_plural, "Catalog items") : "Catalog items";
  const recordsHref = `/admin/orders?merchant_id=${encodeURIComponent(merchant.id)}`;
  const callsHref = `/admin/calls?merchant_id=${encodeURIComponent(merchant.id)}`;
  const overageCost = usage.overage_minutes > 0 ? usage.overage_minutes * (plan.overage_per_minute || 0) : 0;
  const limits = usage.limits ?? detail.entitlements?.limits ?? { minutes: plan.included_minutes, chats: plan.included_chats, sms: plan.included_sms, numbers: plan.phone_numbers };
  const hasChannel = (channel: ChannelKey) => detail.entitlements?.channels?.includes(channel) ?? false;
  const whatsappNumber = merchant.channels?.whatsapp?.number ?? "";
  const messenger = merchant.channels?.messenger;

  return (
    <>
      {backLink}
      <ApiError message={error} />

      <div className="flex flex-col justify-between gap-4 border-b border-border pb-4 md:flex-row md:items-end">
        <div className="min-w-0">
          <h1 className="break-words text-2xl font-semibold">{merchant.business_name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <ActiveBadge active={merchant.active} />
            <Pill tone="teal">{plan.name}</Pill>
            <span className="font-mono text-xs">@{merchant.username}</span>
            <span aria-hidden="true">·</span>
            <span>Created {formatDate(merchant.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
          <Button onClick={() => setOpening(true)} disabled={!merchant.active} title={merchant.active ? undefined : "Activate the account first"}>
            <LogIn className="h-4 w-4" />
            Open portal
          </Button>
          <Button variant="outline" className="text-destructive hover:text-destructive" onClick={() => setDeleting(true)}>
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {!merchant.active && (
        <div className="flex items-start gap-3 rounded-md border border-[#fcd34d] bg-[#fef3c7] p-3 text-sm text-[#92400e] dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            This account is inactive: the owner can&apos;t sign in and the agent doesn&apos;t answer calls or chats. Turn it back on from{" "}
            <button type="button" className="font-semibold underline underline-offset-2" onClick={() => setEditing(true)}>
              Edit
            </button>
            .
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Plan & usage</CardTitle>
            <CardDescription>
              {plan.name} · {planPrice(plan)} · since {formatDate(usage.period_start)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <UsageRow
              label="Call minutes"
              used={usage.minutes}
              limit={limits.minutes}
              unit="min"
              note={
                usage.overage_minutes > 0
                  ? `${num(usage.overage_minutes)} min over the plan${overageCost ? ` (≈ $${overageCost.toFixed(2)} at $${plan.overage_per_minute}/min)` : ""}`
                  : usage.minutes_left !== null
                    ? `${num(usage.minutes_left)} min left`
                    : undefined
              }
            />
            <UsageRow label="Chats" used={usage.chats} limit={limits.chats} unit="chats" />
            <UsageRow label="Texts" used={usage.sms ?? 0} limit={limits.sms} unit="texts" />
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Figure label="Phone calls this period" value={num(usage.calls)} />
              <Figure label={recordsLabel} value={num(detail.records)} href={recordsHref} />
              <Figure label={catalogLabel} value={num(detail.catalog_items)} />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
            <CardDescription>This account&apos;s data.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <ActivityLink href={recordsHref} icon={ClipboardList} title={recordsLabel} detail={`${num(detail.records)} in total`} />
            <ActivityLink href={callsHref} icon={MessagesSquare} title="Calls & chats" detail="Transcripts and recordings" />
          </CardContent>
        </Card>

        <PlanAddonsCard
          merchantId={merchant.id}
          plan={plan}
          entitlements={detail.entitlements}
          requests={detail.addon_requests ?? []}
          catalog={catalog}
          catalogError={catalogError}
          onChanged={() => void load()}
        />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Business type
              <Lock className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
            </CardTitle>
            <CardDescription>Fixed at creation.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="font-semibold">{spec ? t(spec.label, spec.key) : merchant.vertical}</p>
            {spec && <p className="mt-1 text-sm text-muted-foreground">{t(spec.description)}</p>}
            {spec && (
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Records">{t(spec.record_label_plural)}</Row>
                {spec.catalog_kind && <Row label="Catalog">{t(spec.catalog_label_plural, "—")}</Row>}
                <Row label="Agent handles">{spec.directions.map((d) => (d === "inbound" ? "Inbound calls" : "Outbound calls")).join(", ")}</Row>
              </dl>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              <Row label="Owner">{merchant.owner_name || "—"}</Row>
              <Row label="Email">
                {merchant.email ? (
                  <a className="break-all text-primary hover:underline" href={`mailto:${merchant.email}`}>
                    {merchant.email}
                  </a>
                ) : (
                  "—"
                )}
              </Row>
              <Row label="Phone">
                {merchant.phone ? (
                  <a className="text-primary hover:underline" href={`tel:${merchant.phone}`}>
                    {merchant.phone}
                  </a>
                ) : (
                  "—"
                )}
              </Row>
              <Row label="Support phone">{merchant.support_phone || "—"}</Row>
              <Row label="Username">
                <span className="font-mono text-xs">{merchant.username}</span>
              </Row>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Region & agent</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              <Row label="Region">
                {region?.label ?? merchant.region} <span className="text-xs text-muted-foreground">({merchant.region})</span>
              </Row>
              <Row label="Time zone">{merchant.timezone || "—"}</Row>
              <Row label="Currency">{merchant.currency || "—"}</Row>
              <Row label="Emergency number">{merchant.emergency_number || "—"}</Row>
              <Row label="Language">{languageLabel(merchant.language)}</Row>
              <Row label="Voice">{merchant.voice_persona === "male" ? "Male" : "Female"}</Row>
              <Row label="Greeting">
                {merchant.custom_greeting ? <span className="italic">“{merchant.custom_greeting}”</span> : <span className="text-muted-foreground">Standard</span>}
              </Row>
            </dl>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Channels</CardTitle>
            <CardDescription>Where this account&apos;s agent answers.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Channel
              icon={PhoneIncoming}
              title="Inbound number"
              ok={Boolean(merchant.inbound_number)}
              value={merchant.inbound_number ? <span className="font-mono">{merchant.inbound_number}</span> : "Not assigned"}
              hint={merchant.inbound_number ? "Calls reach this agent." : <EditLink onClick={() => setEditing(true)}>Assign number</EditLink>}
            />
            <Channel
              icon={Globe}
              title="Website chat"
              ok={hasChannel("web_chat") && merchant.widget_enabled && Boolean(merchant.widget_key)}
              value={!hasChannel("web_chat") ? "Not on plan" : merchant.widget_enabled ? "Enabled" : "Disabled"}
              hint={!hasChannel("web_chat") ? "Add-on off." : merchant.widget_key ? "Embed key issued." : "The owner turns it on."}
            />
            <Channel
              icon={MessageCircle}
              title="WhatsApp"
              ok={hasChannel("whatsapp") && Boolean(whatsappNumber)}
              value={whatsappNumber ? <span className="font-mono">{whatsappNumber}</span> : "No number"}
              hint={
                !hasChannel("whatsapp") ? (
                  "Add-on off."
                ) : whatsappNumber ? (
                  "Twilio WhatsApp sender."
                ) : (
                  <EditLink onClick={() => setEditing(true)}>Set number</EditLink>
                )
              }
            />
            <Channel
              icon={MessagesSquare}
              title="Messenger"
              ok={hasChannel("messenger") && Boolean(messenger?.connected)}
              value={messenger?.connected ? messenger.page_name || "Page connected" : "Not connected"}
              hint={!hasChannel("messenger") ? "Add-on off." : messenger?.connected ? "Connected by the owner." : "The owner connects a Page."}
            />
            <Channel
              icon={Webhook}
              title="Webhook"
              ok={Boolean(merchant.webhook_url)}
              value={merchant.webhook_url ? "Configured" : "Not configured"}
              hint={merchant.webhook_url ? <span className="break-all">{hostOf(merchant.webhook_url)}</span> : "Set by the owner."}
            />
          </CardContent>
          {merchant.auto_call_at && (
            <CardContent className="pt-0 text-sm text-muted-foreground">
              Next scheduled call run: {formatDateTime(merchant.auto_call_at)}
              {merchant.auto_call_repeat_daily ? " (repeats daily)" : ""}
            </CardContent>
          )}
        </Card>
      </div>

      <MerchantEditDrawer
        merchant={editing ? merchant : null}
        meta={meta}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          void load();
        }}
      />
      <OpenPortalDialog merchant={opening ? merchant : null} onClose={() => setOpening(false)} />
      <DeleteMerchantDialog
        merchant={deleting ? merchant : null}
        onClose={() => setDeleting(false)}
        onDeleted={() => {
          setDeleting(false);
          router.replace("/admin/merchants");
        }}
      />
    </>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr] gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function EditLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="font-semibold text-primary hover:underline">
      {children}
    </button>
  );
}

/** Used vs. the monthly limit (plan + add-ons); null = no limit, 0 = not included. */
function UsageRow({ label, used, limit, unit, note }: { label: string; used: number; limit: number | null; unit: string; note?: string }) {
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span className="font-semibold">{label}</span>
        <span>
          <span className="font-semibold">{num(used)}</span>
          <span className="text-muted-foreground"> / {limit === null ? "unlimited" : limit > 0 ? `${num(limit)} ${unit}` : "not included"}</span>
        </span>
      </div>
      {limit ? (
        <div className="mt-2">
          <Meter value={used} max={limit} label={`${label} used`} />
        </div>
      ) : null}
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

function Figure({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">
        {href ? (
          <Link href={href} className="hover:text-primary hover:underline">
            {value}
          </Link>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

function ActivityLink({
  href,
  icon: Icon,
  title,
  detail,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-3 rounded-md border border-border p-3 transition-colors hover:border-tint-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-xs text-muted-foreground">{detail}</span>
      </span>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" aria-hidden="true" />
    </Link>
  );
}

function Channel({
  icon: Icon,
  title,
  ok,
  value,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  ok: boolean;
  value: React.ReactNode;
  hint: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
        </span>
        <Pill tone={ok ? "green" : "neutral"}>{ok ? "Ready" : "Off"}</Pill>
      </div>
      <p className="mt-2 text-sm">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
