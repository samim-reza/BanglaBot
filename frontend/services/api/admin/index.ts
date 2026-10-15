/** The admin console's API, one module per domain. The barrel (`@/services/api`) re-exports `adminApi`;
 * the newer domains are imported from their own module (`@/services/api/admin/users`, …). */

export { adminApi } from "./accounts";
export type { AdminCallParams, AdminInquiryParams, AdminOrderParams } from "./accounts";
