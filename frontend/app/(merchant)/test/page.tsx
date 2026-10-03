"use client";

import { PageHeader } from "@/components/page-header";
import { TestConsole } from "@/components/test-console";

export default function TestAgentPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Test your agent"
        subtitle="Talk to it through your microphone or chat with it — the same agent your customers reach, without dialing anyone."
      />
      <TestConsole />
    </div>
  );
}
