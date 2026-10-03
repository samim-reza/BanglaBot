/** The account's catalog: doctors / listings / services the agent answers and books from. */

import { rawRequest, request } from "./client";
import type { CatalogImportResult, CatalogItem, CatalogItemInput } from "./types";

export const catalogApi = {
  list: () => request<CatalogItem[]>("/api/catalog", { auth: "merchant" }),
  create: (values: CatalogItemInput) =>
    request<CatalogItem>("/api/catalog", { method: "POST", auth: "merchant", body: JSON.stringify(values) }),
  update: (id: string, values: CatalogItemInput) =>
    request<CatalogItem>(`/api/catalog/${encodeURIComponent(id)}`, {
      method: "PATCH",
      auth: "merchant",
      body: JSON.stringify(values),
    }),
  remove: (id: string) => request<void>(`/api/catalog/${encodeURIComponent(id)}`, { method: "DELETE", auth: "merchant" }),
  /** CSV text with a header row of field keys (or labels). */
  importCsv: (csv: string, replace = false) =>
    request<CatalogImportResult>("/api/catalog/import", {
      method: "POST",
      auth: "merchant",
      body: JSON.stringify({ csv, replace }),
    }),
  templateCsv: async () => {
    const response = await rawRequest("/api/catalog/template.csv", { auth: "merchant" });
    return response.text();
  },
};
