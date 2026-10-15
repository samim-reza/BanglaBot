"use client";

/**
 * Account settings, in tabs (`?tab=business|agent|payments|notifications|calendar|developers|security`).
 * Each card keeps its own draft, dirty state and Save button. Values come from
 * the workspace (`useWorkspace()`); after a save the card adopts what the server
 * returned and the workspace is refreshed so the shell updates too. Tabs mount
 * on first visit and stay mounted, so unsaved edits survive switching tabs.
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import {
  CalendarSection,
  IntegrationsPlaceholder,
  SmsSection,
  useGoogleCalendarReturn,
  useIntegrations,
} from "@/components/portal/integrations-sections";
import { WebhookSection } from "@/components/portal/webhook-section";
import { AgentSection } from "@/components/settings/agent-section";
import { BusinessSettingsSection } from "@/components/settings/business-settings-section";
import { KnowledgeSection } from "@/components/settings/knowledge-section";
import { PaymentsSection } from "@/components/settings/payments-section";
import { ProfileSection } from "@/components/settings/profile-section";
import { RegionSection } from "@/components/settings/region-section";
import { SecuritySection, SessionsSection } from "@/components/settings/security-section";
import { SettingsTabs, TABS, TabPanel, type TabKey } from "@/components/settings/settings-tabs";
import { DirtyContext } from "@/components/settings/shared";
import { useWorkspace } from "@/lib/workspace";
import { type Integrations } from "@/services/api";

function SettingsView() {
  const { merchant, vertical } = useWorkspace();
  const searchParams = useSearchParams();
  const [dirty, setDirty] = useState<Record<string, boolean>>({});

  const tabs = useMemo(() => TABS.filter((tab) => tab.key !== "calendar" || vertical.scheduled), [vertical.scheduled]);
  const resolve = useCallback((value: string | null): TabKey | null => tabs.find((tab) => tab.key === value)?.key ?? null, [tabs]);

  // The address decides the tab (?tab=…); follow it when it changes (links, Google's redirect).
  const urlTab = searchParams.get("tab");
  const [active, setActive] = useState<TabKey>(() => resolve(urlTab) ?? tabs[0].key);
  const [seenUrlTab, setSeenUrlTab] = useState(urlTab);
  if (urlTab !== seenUrlTab) {
    setSeenUrlTab(urlTab);
    const next = resolve(urlTab);
    if (next && next !== active) setActive(next);
  }

  // Tabs mount on first visit and then stay mounted (drafts survive switching).
  const [visited, setVisited] = useState<TabKey[]>([active]);
  if (!visited.includes(active)) setVisited([...visited, active]);
  const mounted = (key: TabKey) => key === active || visited.includes(key);

  const select = useCallback((key: TabKey) => {
    setActive(key);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", key);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, []);

  // Old #section links (e.g. /settings#knowledge): open the tab that holds the card and scroll to it.
  const anchor = useRef<string | null>(null);
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    anchor.current = hash;
    if (!resolve(new URLSearchParams(window.location.search).get("tab"))) {
      const owner = tabs.find((tab) => tab.sections.includes(hash));
      if (owner) setActive(owner.key);
    }
  }, [resolve, tabs]);

  useGoogleCalendarReturn();

  // SMS + calendar share one load, started the first time either tab opens.
  const needsIntegrations = mounted("notifications") || mounted("calendar");
  const integrations = useIntegrations(needsIntegrations);
  const integrationsLoaded = integrations.data !== null;

  useEffect(() => {
    const id = anchor.current;
    if (!id) return;
    const node = document.getElementById(id);
    if (node && !node.closest("[hidden]")) {
      node.scrollIntoView({ block: "start" });
      anchor.current = null;
    }
  }, [active, integrationsLoaded]);

  const report = useCallback((id: string, value: boolean) => {
    setDirty((current) => (Boolean(current[id]) === value ? current : { ...current, [id]: value }));
  }, []);
  const anyDirty = Object.values(dirty).some(Boolean);

  // Warn before leaving the page with unsaved edits.
  useEffect(() => {
    if (!anyDirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [anyDirty]);

  const integrationsBody = (render: (data: Integrations) => React.ReactNode) =>
    integrations.data ? render(integrations.data) : <IntegrationsPlaceholder error={integrations.error} onRetry={() => void integrations.reload()} />;

  return (
    <DirtyContext.Provider value={report}>
      <div className="mx-auto max-w-4xl space-y-6">
        <PageHeader title="Settings" subtitle={`Signed in as ${merchant.username}`} />

        <SettingsTabs tabs={tabs} active={active} dirty={dirty} onSelect={select} />

        {mounted("business") && (
          <TabPanel tab="business" active={active === "business"}>
            <ProfileSection />
            <RegionSection />
            <BusinessSettingsSection />
          </TabPanel>
        )}
        {mounted("agent") && (
          <TabPanel tab="agent" active={active === "agent"}>
            <AgentSection />
            <KnowledgeSection />
          </TabPanel>
        )}
        {mounted("payments") && (
          <TabPanel tab="payments" active={active === "payments"}>
            <PaymentsSection />
          </TabPanel>
        )}
        {mounted("notifications") && (
          <TabPanel tab="notifications" active={active === "notifications"}>
            {integrationsBody((data) => (
              <SmsSection data={data} onSaved={integrations.setData} />
            ))}
          </TabPanel>
        )}
        {vertical.scheduled && mounted("calendar") && (
          <TabPanel tab="calendar" active={active === "calendar"}>
            {integrationsBody((data) => (
              <CalendarSection data={data} onSaved={integrations.setData} />
            ))}
          </TabPanel>
        )}
        {mounted("developers") && (
          <TabPanel tab="developers" active={active === "developers"}>
            <WebhookSection />
          </TabPanel>
        )}
        {mounted("security") && (
          <TabPanel tab="security" active={active === "security"}>
            <SecuritySection />
            <SessionsSection />
          </TabPanel>
        )}
      </div>
    </DirtyContext.Provider>
  );
}

export default function SettingsPage() {
  // useSearchParams needs a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <SettingsView />
    </Suspense>
  );
}
