"use client";

import { PageHeader } from "@/components/page-header";
import { TestConsole } from "@/components/test-console";

export default function TestAgentPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Test your agent" subtitle="Call or chat with it from your browser." />
      <TestConsole />
    </div>
  );
}
