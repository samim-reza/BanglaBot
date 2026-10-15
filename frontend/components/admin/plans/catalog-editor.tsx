"use client";

import { useState } from "react";

import { Segments } from "@/components/agent-flow/bits";
import { LoadingRows } from "@/components/admin/states";
import { SaveBar } from "@/components/admin/save-bar";
import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";

import { AddonsTable } from "./addons-table";
import { TiersTable } from "./tiers-table";
import { useCatalog } from "./use-catalog";

/** Tiers and add-ons, edited together and saved as one catalog. */
export function CatalogEditorView({ editable }: { editable: boolean }) {
  const editor = useCatalog();
  const toast = useAppToast();
  const [view, setView] = useState<"tiers" | "addons">("tiers");

  if (!editor.saved) return editor.loadError ? <ApiError message={editor.loadError} /> : <LoadingRows label="Loading the catalog…" rows={6} />;

  const general = editor.errors.general;
  const tierErrors = Object.keys({ ...editor.errors.rows, ...editor.errors.fields }).some((key) => key.startsWith("tiers."));
  const addonErrors = Object.keys({ ...editor.errors.rows, ...editor.errors.fields }).some((key) => key.startsWith("addons."));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segments
          label="Catalog"
          value={view}
          onChange={setView}
          options={[
            { value: "tiers", label: `Tiers (${editor.tiers.length})${tierErrors ? " ⚠" : ""}` },
            { value: "addons", label: `Add-ons (${editor.addons.length})${addonErrors ? " ⚠" : ""}` },
          ]}
        />
        {!editable && <span className="text-xs text-muted-foreground">Read-only · superadmins edit</span>}
      </div>
      {general.length > 0 && <ApiError message={general.join(" · ")} />}
      {view === "tiers" ? <TiersTable editor={editor} editable={editable} /> : <AddonsTable editor={editor} editable={editable} />}
      <SaveBar
        dirty={editor.dirty}
        saving={editor.saving}
        onDiscard={editor.discard}
        onSave={() => void editor.save().then((ok) => ok && toast.success("Catalog saved."))}
      />
    </div>
  );
}
