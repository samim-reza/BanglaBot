/** Browser-side token storage for the merchant workspace and the admin console.
 *
 * Both JWTs live in localStorage and are sent as `Authorization: Bearer` by the
 * client. Only one of the two is ever meaningful at a time — signing in to one
 * surface clears the other so a stale token can't bounce the user between them.
 */

import type { Merchant } from "./types";

const MERCHANT_TOKEN_KEY = "callisa_merchant_token";
const MERCHANT_KEY = "callisa_merchant";
const ADMIN_TOKEN_KEY = "callisa_admin_token";

/** Keys from before the Callisa rename, moved to the new keys once so signed-in users stay signed in. */
const LEGACY_KEYS: [string, string][] = [
  ["banglabot_merchant_token", MERCHANT_TOKEN_KEY],
  ["banglabot_merchant", MERCHANT_KEY],
  ["banglabot_admin_token", ADMIN_TOKEN_KEY],
];
let legacyMigrated = false;

function migrateLegacyKeys(store: Storage) {
  legacyMigrated = true;
  try {
    for (const [legacy, key] of LEGACY_KEYS) {
      const value = store.getItem(legacy);
      if (value === null) continue;
      if (store.getItem(key) === null) store.setItem(key, value);
      store.removeItem(legacy);
    }
  } catch {
    // storage full or blocked: the old keys just stay where they are
  }
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  const store = window.localStorage;
  if (!legacyMigrated) migrateLegacyKeys(store);
  return store;
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

/** Swap in a re-issued token (password change, "sign out everywhere") and keep the profile. */
export function saveMerchantToken(token: string) {
  if (token) storage()?.setItem(MERCHANT_TOKEN_KEY, token);
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
