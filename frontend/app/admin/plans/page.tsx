"use client";

import Link from "next/link";
import { Puzzle } from "lucide-react";

import { CatalogEditorView } from "@/components/admin/plans/catalog-editor";
import { SignupSettingsCard } from "@/components/admin/plans/signup-settings-card";
import { VerticalsCard } from "@/components/admin/plans/verticals-card";
import { useAdminMe } from "@/components/admin/shell/admin-me";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

export default function AdminPlansPage() {
  const { can } = useAdminMe();
  const editable = can("editCatalog");
  return (
    <>
      <PageHeader
        title="Plans & add-ons"
        subtitle="Prices in USD."
        actions={
          <Button asChild variant="outline">
            <Link href="/admin/requests">
              <Puzzle className="h-4 w-4" />
              Add-on requests
            </Link>
          </Button>
        }
      />
      <CatalogEditorView editable={editable} />
      <div className="grid gap-6 lg:grid-cols-2">
        <SignupSettingsCard editable={editable} />
        <VerticalsCard editable={editable} />
      </div>
    </>
  );
}
