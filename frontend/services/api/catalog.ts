/** The account's catalog: doctors / listings / services the agent answers and books from.
 *
 * `kind` picks one of the vertical's catalog kinds and is sent as `?kind=` only when
 * given (the primary kind otherwise). Items are addressed by id for update / delete.
 */

import { queryString, rawRequest, request } from "./client";
import type { CatalogImportResult, CatalogItem, CatalogItemInput } from "./types";

const withKind = (path: string, kind?: string) => `${path}${queryString({ kind })}`;

export const catalogApi = {
  list: (kind?: string) => request<CatalogItem[]>(withKind("/api/catalog", kind), { auth: "merchant" }),
  create: (values: CatalogItemInput, kind?: string) =>
    request<CatalogItem>(withKind("/api/catalog", kind), { method: "POST", auth: "merchant", body: JSON.stringify(values) }),
  update: (id: string, values: CatalogItemInput) =>
    request<CatalogItem>(`/api/catalog/${encodeURIComponent(id)}`, {
      method: "PATCH",
      auth: "merchant",
      body: JSON.stringify(values),
    }),
  remove: (id: string) => request<void>(`/api/catalog/${encodeURIComponent(id)}`, { method: "DELETE", auth: "merchant" }),
  /** CSV text with a header row of field keys (or labels). */
  importCsv: (csv: string, replace = false, kind?: string) =>
    request<CatalogImportResult>(withKind("/api/catalog/import", kind), {
      method: "POST",
      auth: "merchant",
      body: JSON.stringify({ csv, replace }),
    }),
  templateCsv: async (kind?: string) => {
    const response = await rawRequest(withKind("/api/catalog/template.csv", kind), { auth: "merchant" });
    return response.text();
  },
};
