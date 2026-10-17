/** The API client, as a package. Import from `@/services/api`. */

export { API_BASE, ApiRequestError, formatApiError, isApiRequestError, queryString, rawRequest, request } from "./client";
export type { AuthScope, RequestOptions } from "./client";

export {
  adminToken,
  clearAdminSession,
  clearMerchantSession,
  getMerchantSession,
  merchantToken,
  saveAdminSession,
  saveMerchantProfile,
  saveMerchantSession,
  saveMerchantToken,
} from "./session";

export * from "./types";

export { merchantApi } from "./merchant";
export { ordersApi } from "./orders";
export type { OrderListParams } from "./orders";
export { catalogApi } from "./catalog";
export { callsApi } from "./calls";
export type { CallListParams } from "./calls";
export { integrationsApi } from "./integrations";
export { addonsApi, channelsApi } from "./addons";
export { publicApi } from "./public";
export { agentFlowApi, flowErrors } from "./agentFlow";
export type * from "./agentFlow";
export { billingApi } from "./billing";
export { dashboardApi } from "./dashboard";
export type { DashboardRange, DashboardSummary, OutboundSummary } from "./dashboard";
export { closuresApi } from "./closures";
export type { Closure, ClosureInput, ClosuresView } from "./closures";
export { phoneLineApi } from "./phoneLine";
export type { PhoneLineView } from "./phoneLine";
export type * from "./billing";
export { signupApi } from "./signup";
export type * from "./signup";
export { payApi, paymentsApi } from "./pay";
export type * from "./pay";
export { adminApi } from "./admin";
export type { AdminCallParams, AdminInquiryParams, AdminOrderParams } from "./admin";
