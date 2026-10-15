import { Globe, MessageCircle, MessagesSquare, PhoneIncoming, Webhook } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import type { AdminMerchantDetail, ChannelKey } from "@/services/api";

import { Channel, EditLink, hostOf } from "./account-bits";

/** Where this account's agent answers. */
export function ChannelsCard({ detail, onEdit }: { detail: AdminMerchantDetail; onEdit: () => void }) {
  const { merchant } = detail;
  const hasChannel = (channel: ChannelKey) => detail.entitlements?.channels?.includes(channel) ?? false;
  const whatsappNumber = merchant.channels?.whatsapp?.number ?? "";
  const messenger = merchant.channels?.messenger;

  return (
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
          hint={merchant.inbound_number ? "Calls reach this agent." : <EditLink onClick={onEdit}>Assign number</EditLink>}
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
          hint={!hasChannel("whatsapp") ? "Add-on off." : whatsappNumber ? "Twilio WhatsApp sender." : <EditLink onClick={onEdit}>Set number</EditLink>}
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
  );
}
