/** Browser-side token storage for the merchant workspace and the admin console.
 *
 * Both JWTs live in localStorage and are sent as `Authorization: Bearer` by the
 * client. Only one of the two is ever meaningful at a time — signing in to one
 * surface clears the other so a stale token can't bounce the user between them.
 */

import type { Merchant } from "./types";

const MERCHANT_TOKEN_KEY = "banglabot_merchant_token";
const MERCHANT_KEY = "banglabot_merchant";
const ADMIN_TOKEN_KEY = "banglabot_admin_token";

function storage(): Storage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

export function merchantToken(): string {
  return storage()?.getItem(MERCHANT_TOKEN_KEY) ?? "";
}

export function getMerchantSession(): { token: string; merchant: Merchant | null } {
  const store = storage();
  if (!store) return { token: "", merchant: null };
  const raw = store.getItem(MERCHANT_KEY);
  let merchant: Merchant | null = null;
  if (raw) {
    try {
      merchant = JSON.parse(raw) as Merchant;
    } catch {
      merchant = null;
    }
  }
  return { token: store.getItem(MERCHANT_TOKEN_KEY) ?? "", merchant };
}

export function saveMerchantSession(token: string, merchant: Merchant) {
  const store = storage();
  if (!store) return;
  store.setItem(MERCHANT_TOKEN_KEY, token);
  store.setItem(MERCHANT_KEY, JSON.stringify(merchant));
  store.removeItem(ADMIN_TOKEN_KEY);
}

/** Refresh the cached merchant profile without touching the token. */
export function saveMerchantProfile(merchant: Merchant) {
  storage()?.setItem(MERCHANT_KEY, JSON.stringify(merchant));
}

export function clearMerchantSession() {
  const store = storage();
  if (!store) return;
  store.removeItem(MERCHANT_TOKEN_KEY);
  store.removeItem(MERCHANT_KEY);
}

export function adminToken(): string {
  return storage()?.getItem(ADMIN_TOKEN_KEY) ?? "";
}

export function saveAdminSession(token: string) {
  const store = storage();
  if (!store) return;
  store.setItem(ADMIN_TOKEN_KEY, token);
  store.removeItem(MERCHANT_TOKEN_KEY);
  store.removeItem(MERCHANT_KEY);
}

export function clearAdminSession() {
  storage()?.removeItem(ADMIN_TOKEN_KEY);
}
