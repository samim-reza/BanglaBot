"use client";

/** Where customers reach the agent: phone, website chat, WhatsApp and Messenger (locked ones link to their add-on). */

import Link from "next/link";
import { ArrowRight, MessageCircle, MessageCircleMore, MessageSquare, Phone } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { LockedAddon, LockedCard, MessengerSection, WhatsAppSection, useChannelsView } from "@/components/portal/channel-sections";
import { OutboundSection, PhoneLineSection, RecordingsSection } from "@/components/portal/phone-sections";
import { useAddonActions, useAddonShop, useHashTarget } from "@/components/portal/plan-section";
import { WidgetSection } from "@/components/portal/widget-section";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import type { ChannelKey } from "@/services/api";

export default function ChannelsPage() {
  const { vertical, entitlements } = useWorkspace();
  const { shop, setShop } = useAddonShop();
  const actions = useAddonActions(setShop);
  const { view, setView } = useChannelsView();
  useHashTarget(true);
  const has = (channel: ChannelKey) => entitlements.channels.includes(channel);
  const outbound = vertical.directions.includes("outbound");

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="Channels" subtitle="Where customers reach your agent." />

      {has("voice") ? (
        <>
          <PhoneLineSection />
          <div className={cn("grid gap-6", outbound && "md:grid-cols-2")}>
            {outbound && <OutboundSection />}
            <RecordingsSection />
          </div>
        </>
      ) : (
        <LockedCard
          id="phone"
          icon={Phone}
          title="Phone agent"
          line="On voice plans."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/contact?plan=starter" target="_blank" rel="noopener">
                See voice plans
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            </Button>
          }
        />
      )}

      {has("web_chat") ? (
        <WidgetSection />
      ) : (
        <LockedAddon id="web-chat" addonKey="web_chat" icon={MessageSquare} title="Website chat" shop={shop} actions={actions} />
      )}

      {has("whatsapp") ? (
        <WhatsAppSection view={view} />
      ) : (
        <LockedAddon id="whatsapp" addonKey="whatsapp" icon={MessageCircle} title="WhatsApp" shop={shop} actions={actions} />
      )}

      {has("messenger") ? (
        <MessengerSection view={view} onView={setView} />
      ) : (
        <LockedAddon id="messenger" addonKey="messenger" icon={MessageCircleMore} title="Messenger" shop={shop} actions={actions} />
      )}
    </div>
  );
}
