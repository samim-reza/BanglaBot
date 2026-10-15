"use client";

import { Suspense, useMemo } from "react";
import Link from "next/link";

import { CatalogBoard } from "@/components/catalog/catalog-board";
import { KindCatalog } from "@/components/catalog/kind-catalog";
import { catalogKinds } from "@/components/catalog/kinds";
import { EmptyState, PageHeader } from "@/components/page-header";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";

export default function CatalogPage() {
  const { vertical } = useWorkspace();
  const kinds = useMemo(() => catalogKinds(vertical), [vertical]);

  if (!kinds.length) {
    return (
      <div className="space-y-6">
        <PageHeader title="Catalog" />
        <EmptyState title={`Your agent works from your ${t(vertical.record_label_plural, "records").toLowerCase()}, not a catalog.`}>
          <Link href="/orders" className="font-medium text-primary-dark hover:underline">
            Open {t(vertical.record_label_plural, "records").toLowerCase()}
          </Link>
        </EmptyState>
      </div>
    );
  }

  if (kinds.length === 1) return <CatalogBoard spec={kinds[0]} primary />;

  return (
    <div className="space-y-6">
      <PageHeader title={t(vertical.catalog_label_plural, "Catalog")} subtitle="Your agent only offers what's listed here." />
      {/* useSearchParams (?kind=) needs a Suspense boundary. */}
      <Suspense fallback={null}>
        <KindCatalog kinds={kinds} />
      </Suspense>
    </div>
  );
}
