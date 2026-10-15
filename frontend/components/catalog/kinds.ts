import type { CatalogKindSpec, VerticalSpec } from "@/services/api";

/** The vertical's catalog kinds, primary first. Older backends only send `catalog_kind` / `catalog_fields`. */
export function catalogKinds(vertical: VerticalSpec): CatalogKindSpec[] {
  if (vertical.catalog_kinds?.length) return vertical.catalog_kinds;
  if (!vertical.catalog_kind) return [];
  return [
    {
      kind: vertical.catalog_kind,
      label: vertical.catalog_label,
      label_plural: vertical.catalog_label_plural,
      fields: vertical.catalog_fields,
    },
  ];
}
