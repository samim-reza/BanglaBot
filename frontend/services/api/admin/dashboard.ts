/** The dashboard's overview figures (GET /api/admin/overview). */

import { request } from "../client";
import type { AdminOverview } from "../types";

/** `minutes_today` is a slot for when the overview reports it (backend gap today). */
export type DashboardOverview = AdminOverview & { minutes_today?: number };

export const dashboardApi = {
  overview: () => request<DashboardOverview>("/api/admin/overview", { auth: "admin" }),
};
