"use client";

/** Where customers reach the agent: phone, website chat, WhatsApp, Messenger, Instagram (locked ones link to their add-on). */

import Link from "next/link";
import { ArrowRight, Camera, MessageCircle, MessageCircleMore, MessageSquare, Phone } from "lucide-react";

import { ChannelStates } from "@/components/channels/channel-states";
import { MetaConnectSection } from "@/components/channels/meta-connect";
import { PageHeader } from "@/components/page-header";
import { LockedAddon, LockedCard, MessengerSection, WhatsAppSection, useChannelsView } from "@/components/portal/channel-sections";
import { OutboundSection, PhoneLineSection, RecordingsSection } from "@/components/portal/phone-sections";
import { useAddonActions, useAddonShop, useHashTarget } from "@/components/portal/plan-section";
import { WidgetSection } from "@/components/portal/widget-section";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { channelsApi, type ChannelKey } from "@/services/api";

export default function ChannelsPage() {
  const { vertical, entitlements } = useWorkspace();
  const { shop, setShop } = useAddonShop();
  const actions = useAddonActions(setShop);
  const { view, setView } = useChannelsView();
  useHashTarget(true);
  const has = (channel: ChannelKey) => entitlements.channels.includes(channel);
  const outbound = vertical.directions.includes("outbound");
  const instagramState = view?.status?.find((row) => row.channel === "instagram");
  const showInstagram = has("instagram") || Boolean(instagramState && instagramState.state !== "unavailable");

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="Channels" subtitle="Where customers reach your agent." />
      {view?.status && <ChannelStates rows={view.status} />}

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
        <>
          <WhatsAppSection view={view} />
          {view?.whatsapp_cloud && (
            <MetaConnectSection
              id="whatsapp-cloud"
              icon={MessageCircle}
              title="Your WhatsApp number"
              connected={view.whatsapp_cloud.connected}
              summary={[view.whatsapp_cloud.name, view.whatsapp_cloud.display_number].filter(Boolean).join(" · ")}
              idLabel="Phone number ID"
              tokenLabel="Access token"
              help="Meta Business → WhatsApp → API setup: copy the phone number ID and a permanent access token."
              platformReady={view.platform.whatsapp_cloud_ready !== false}
              connect={channelsApi.connectWhatsAppCloud}
              disconnect={channelsApi.disconnectWhatsAppCloud}
              onView={setView}
            />
          )}
        </>
      ) : (
        <LockedAddon id="whatsapp" addonKey="whatsapp" icon={MessageCircle} title="WhatsApp" shop={shop} actions={actions} />
      )}

      {has("messenger") ? (
        <MessengerSection view={view} onView={setView} />
      ) : (
        <LockedAddon id="messenger" addonKey="messenger" icon={MessageCircleMore} title="Messenger" shop={shop} actions={actions} />
      )}

      {showInstagram &&
        (has("instagram") && view?.instagram ? (
          <MetaConnectSection
            id="instagram"
            icon={Camera}
            title="Instagram"
            connected={view.instagram.connected}
            summary={view.instagram.username ? `@${view.instagram.username}` : ""}
            idLabel="Instagram account ID"
            tokenLabel="Page access token"
            help="Link the Instagram professional account to your Facebook Page, then copy its account ID and the Page access token from your Meta app."
            platformReady={view.platform.instagram_ready !== false}
            connect={channelsApi.connectInstagram}
            disconnect={channelsApi.disconnectInstagram}
            onView={setView}
          />
        ) : !has("instagram") ? (
          <LockedAddon id="instagram" addonKey={instagramState?.addon || "instagram"} icon={Camera} title="Instagram" shop={shop} actions={actions} />
        ) : null)}
    </div>
  );
}
