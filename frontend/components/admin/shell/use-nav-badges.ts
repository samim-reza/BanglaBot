"use client";

import { useEffect, useState } from "react";

import { ADDON_REQUESTS_CHANGED_EVENT } from "@/components/admin/addon-requests";
import { adminApi, adminToken } from "@/services/api";
import { signupsApi } from "@/services/api/admin/signups";

import { useAdminMe } from "./admin-me";

/** Fired by screens that change inquiry statuses so the nav count refreshes. */
export const INQUIRIES_CHANGED_EVENT = "admin:inquiries-changed";
/** Fired after a signup is approved or rejected. */
export const SIGNUPS_CHANGED_EVENT = "admin:signups-changed";

/** A nav count refreshed on navigation and whenever `event` fires. */
function useCount(enabled: boolean, pathname: string, event: string, load: () => Promise<number>): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled || !adminToken()) return;
    let cancelled = false;
    const refresh = () =>
      load()
        .then((value) => !cancelled && setCount(value))
        .catch(() => undefined);
    void refresh();
    window.addEventListener(event, refresh);
    return () => {
      cancelled = true;
      window.removeEventListener(event, refresh);
    };
    // `load` is a module-level function at each call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, pathname, event]);
  return enabled ? count : 0;
}

const newInquiries = () => adminApi.inquiries({ status: "new", page_size: 1 }).then((page) => page.total);
const pendingRequests = () => adminApi.addonRequests("pending").then((result) => result.items.length);
/** The list is cursor-paged (no total): a full page with more behind it reads as 100+. */
export const signupsToApprove = () =>
  signupsApi.list({ status: "awaiting_approval", limit: 100 }).then((page) => page.items.length + (page.next_cursor ? 1 : 0));

/** New sales inquiries, pending add-on requests and signups to approve, for the nav badges. */
export function useNavBadges(enabled: boolean, pathname: string) {
  const { can } = useAdminMe();
  return {
    inquiries: useCount(enabled, pathname, INQUIRIES_CHANGED_EVENT, newInquiries),
    requests: useCount(enabled, pathname, ADDON_REQUESTS_CHANGED_EVENT, pendingRequests),
    signups: useCount(enabled && can("signups"), pathname, SIGNUPS_CHANGED_EVENT, signupsToApprove),
  };
}
