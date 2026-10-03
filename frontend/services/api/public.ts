/** Public website data and the talk-to-sales form. */

import { request } from "./client";
import type { PublicCatalog, SalesInquiryInput } from "./types";

export const publicApi = {
  catalog: () => request<PublicCatalog>("/api/public/catalog"),
  contact: (values: SalesInquiryInput) =>
    request<{ ok: boolean }>("/api/public/contact", { method: "POST", body: JSON.stringify(values) }),
};
