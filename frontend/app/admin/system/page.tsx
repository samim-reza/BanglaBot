"use client";

import { RefreshCw } from "lucide-react";

import { LoadingRows } from "@/components/admin/states";
import { HealthGrid } from "@/components/admin/system/health-grid";
import { useHealth } from "@/components/admin/system/use-health";
import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

export default function AdminSystemPage() {
  const { health, error, checkedAt, refreshing, reload } = useHealth();
  return (
    <>
      <PageHeader
        title="System"
        subtitle={health ? `${health.environment}${checkedAt ? ` · checked ${checkedAt.toLocaleTimeString()}` : ""}` : undefined}
        actions={
          <Button variant="outline" onClick={() => void reload()} disabled={refreshing} aria-label="Refresh">
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin motion-reduce:animate-none" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        }
      />
      <ApiError message={error} />
      {health ? <HealthGrid health={health} /> : error ? null : <LoadingRows label="Checking the system…" rows={4} />}
    </>
  );
}
