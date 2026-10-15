"use client";

import { ClipboardList, Lock, MessagesSquare, ScrollText } from "lucide-react";

import { PlanAddonsCard } from "@/components/admin/plan-addons-card";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { planPrice, regionOf, verticalOf } from "@/components/admin/use-admin-meta";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, languageLabel } from "@/lib/format";
import { t } from "@/lib/vertical";
import type { AddonItem, AdminMerchantDetail, AdminMeta } from "@/services/api";

import { ActivityLink, Figure, num, Row, UsageRow } from "./account-bits";
import { ChannelsCard } from "./channels-card";

/** The account's plan, usage, profile, agent and channels. */
export function AccountOverview({
  detail,
  meta,
  catalog,
  catalogError,
  onEdit,
  onChanged,
}: {
  detail: AdminMerchantDetail;
  meta: AdminMeta | null;
  catalog: AddonItem[] | null;
  catalogError: string | null;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const { can } = useAdminMe();
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

  return (
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
        </CardHeader>
        <CardContent className="space-y-2">
          <ActivityLink href={recordsHref} icon={ClipboardList} title={recordsLabel} detail={`${num(detail.records)} in total`} />
          <ActivityLink href={callsHref} icon={MessagesSquare} title="Calls & chats" detail="Transcripts and recordings" />
          {can("audit") && (
            <ActivityLink href={`/admin/audit?merchant_id=${encodeURIComponent(merchant.id)}`} icon={ScrollText} title="Audit log" detail="Changes to this account" />
          )}
        </CardContent>
      </Card>

      <PlanAddonsCard
        merchantId={merchant.id}
        plan={plan}
        entitlements={detail.entitlements}
        requests={detail.addon_requests ?? []}
        catalog={catalog}
        catalogError={catalogError}
        onChanged={onChanged}
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

      <ChannelsCard detail={detail} onEdit={onEdit} />
    </div>
  );
}
