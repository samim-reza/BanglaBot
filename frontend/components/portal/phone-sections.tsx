"use client";

/** Phone line, outbound calling and recordings. */

import Link from "next/link";
import { ArrowRight, FileText, Phone, PhoneOutgoing } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCopy, CopyButton, SectionCard, StatusPill, SetupNote } from "@/components/portal/kit";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";

// ---------------------------------------------------------------- phone line / outbound / recordings

export function PhoneLineSection() {
  const { merchant, telephony } = useWorkspace();
  const { copied, copy } = useCopy();
  const number = merchant.inbound_number?.trim();
  const ready = telephony.configured;
  return (
    <SectionCard id="phone" icon={Phone} title="Phone line" badge={<StatusPill ok={ready}>{ready ? "Ready" : "Not set up"}</StatusPill>}>
      <div className="space-y-3 text-sm">
        {number ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-lg font-semibold tabular-nums">{number}</span>
              <CopyButton id="number" text={number} copied={copied} onCopy={copy} />
            </div>
            <p className="text-muted-foreground">Forward your business number here.</p>
          </>
        ) : (
          <p className="text-muted-foreground">No number yet — your admin assigns one.</p>
        )}
        {!ready && <SetupNote>Phone calling isn&apos;t set up on this server yet.</SetupNote>}
        {ready && telephony.platform_number && (
          <p className="text-xs text-muted-foreground">
            Outbound caller ID: <span className="font-mono">{telephony.platform_number}</span>
          </p>
        )}
      </div>
    </SectionCard>
  );
}

export function OutboundSection() {
  const { vertical } = useWorkspace();
  const label = t(vertical.outbound_label, "Outbound call");
  const plural = t(vertical.record_label_plural, "records");
  return (
    <SectionCard id="outbound" icon={PhoneOutgoing} title={`${label}s`} description="Call one, everyone, or on a schedule.">
      <Button asChild variant="outline" size="sm">
        <Link href="/orders">
          Open {plural}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </Button>
    </SectionCard>
  );
}

export function RecordingsSection() {
  const { entitlements } = useWorkspace();
  const yearLong = entitlements.features.includes("recording_retention");
  return (
    <SectionCard
      id="recordings"
      icon={FileText}
      title="Recordings"
      description="Every call and chat gets a transcript."
      badge={yearLong ? <StatusPill ok>Kept 12 months</StatusPill> : undefined}
    >
      <Button asChild variant="outline" size="sm">
        <Link href="/calls">
          Call history
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </Button>
    </SectionCard>
  );
}
