/**
 * Service-type vocabulary: the merchant's vertical (ecommerce/courier) decides
 * what the "thing being called about" is named across the UI. All values are
 * Bengali source strings — render them through t() so the en.ts dictionary
 * translates them like every other string.
 */
import { useEffect, useState } from "react";
import { api } from "./api/client";
import { Merchant } from "./api/types";

export type ServiceType = "ecommerce" | "courier";

export interface ServiceText {
  navOrders: string;
  noun: string;
  newItem: string;
  itemsLabel: string;
  itemsShort: string;
  amountLabel: string;
  amountShort: string;
  refLabel: string;
  customerLabel: string;
  customerShort: string;
  searchPlaceholder: string;
  totalLabel: string;
  callButton: string;
  emptyTitle: string;
  emptyHint: string;
  saveButton: string;
  editButton: string;
  backLabel: string;
  heroLine: string;
}

const TEXT: Record<ServiceType, ServiceText> = {
  ecommerce: {
    navOrders: "অর্ডারসমূহ",
    noun: "অর্ডার",
    newItem: "নতুন অর্ডার",
    itemsLabel: "পণ্যের বিবরণ",
    itemsShort: "পণ্য",
    amountLabel: "মোট মূল্য (টাকা)",
    amountShort: "মূল্য",
    refLabel: "অর্ডার নম্বর (ঐচ্ছিক)",
    customerLabel: "কাস্টমারের নাম *",
    customerShort: "কাস্টমার",
    searchPlaceholder: "নাম / ফোন / অর্ডার নম্বর খুঁজুন",
    totalLabel: "মোট অর্ডার",
    callButton: "কল করে নিশ্চিত করুন",
    emptyTitle: "কোনো অর্ডার নেই",
    emptyHint: "প্রথম অর্ডার যোগ করলেই এআই কল শুরু করা যাবে",
    saveButton: "অর্ডার সংরক্ষণ করুন",
    editButton: "অর্ডার সম্পাদনা",
    backLabel: "সব অর্ডার",
    heroLine: "আজকের অর্ডার তুলুন — কনফার্মেশন কলের দায়িত্ব BanglaBot-এর।",
  },
  courier: {
    navOrders: "পার্সেলসমূহ",
    noun: "পার্সেল",
    newItem: "নতুন পার্সেল",
    itemsLabel: "পার্সেলের বিবরণ",
    itemsShort: "পার্সেল",
    amountLabel: "সিওডি টাকা (ক্যাশ অন ডেলিভারি)",
    amountShort: "সিওডি",
    refLabel: "ট্র্যাকিং নম্বর (ঐচ্ছিক)",
    customerLabel: "প্রাপকের নাম *",
    customerShort: "প্রাপক",
    searchPlaceholder: "নাম / ফোন / ট্র্যাকিং নম্বর খুঁজুন",
    totalLabel: "মোট পার্সেল",
    callButton: "কল করে ডেলিভারি নিশ্চিত করুন",
    emptyTitle: "কোনো পার্সেল নেই",
    emptyHint: "প্রথম পার্সেল যোগ করলেই এআই ডেলিভারি কল শুরু করা যাবে",
    saveButton: "পার্সেল সংরক্ষণ করুন",
    editButton: "পার্সেল সম্পাদনা",
    backLabel: "সব পার্সেল",
    heroLine: "আজকের পার্সেল তুলুন — ডেলিভারি কলের দায়িত্ব BanglaBot-এর।",
  },
};

/** Order statuses a merchant may (re-)call. Rescheduled parcels stay callable. */
export const CALLABLE_STATUSES = ["pending", "no_answer", "needs_review", "rescheduled"];

let cached: ServiceType | null = null;
let pending: Promise<ServiceType> | null = null;

/** Reset the cached service type (call on logout/login). */
export function clearServiceCache() {
  cached = null;
  pending = null;
}

/**
 * The logged-in merchant's service type, fetched once per session.
 * Renders as "ecommerce" until known so first paint never flashes wrong data
 * for the majority vertical. Pass enabled=false for admin screens.
 */
export function useServiceType(enabled = true): ServiceType {
  const [service, setService] = useState<ServiceType>(cached ?? "ecommerce");
  useEffect(() => {
    if (!enabled || cached) return;
    pending ??= api<Merchant>("/api/auth/me").then(
      (m) => (cached = m.service_type === "courier" ? "courier" : "ecommerce")
    );
    let alive = true;
    pending.then((s) => alive && setService(s)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [enabled]);
  return service;
}

export function serviceText(service: ServiceType): ServiceText {
  return TEXT[service];
}
