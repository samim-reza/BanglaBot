/** Add-ons wired to outside services: SMS confirmations and calendar sync. */

import { queryString, request } from "./client";
import type { CalendarCheck, GoogleCalendarOption, Integrations, Page, SmsMessage, SmsSettings } from "./types";

const json = (method: string, body: unknown) => ({ method, auth: "merchant" as const, body: JSON.stringify(body) });

export const integrationsApi = {
  get: () => request<Integrations>("/api/integrations", { auth: "merchant" }),

  // SMS
  updateSms: (values: Partial<SmsSettings>) => request<Integrations>("/api/integrations/sms", json("PATCH", values)),
  testSms: (to: string) => request<SmsMessage>("/api/integrations/sms/test", json("POST", { to })),
  messages: (params: { order_id?: string; page?: number; page_size?: number } = {}) =>
    request<Page<SmsMessage>>(`/api/integrations/messages${queryString(params)}`, { auth: "merchant" }),
  /** Empty body = the standard confirmation text for the record. */
  sendRecordSms: (orderId: string, body = "") =>
    request<SmsMessage>(`/api/integrations/messages/order/${encodeURIComponent(orderId)}`, json("POST", { body })),

  // Calendar
  updateCalendar: (values: { busy_ics_urls: string[] }) => request<Integrations>("/api/integrations/calendar", json("PATCH", values)),
  rotateFeed: () => request<Integrations>("/api/integrations/calendar/feed-token", { method: "POST", auth: "merchant" }),
  checkCalendar: (url: string) => request<CalendarCheck>("/api/integrations/calendar/check", json("POST", { url })),
  updateItemCalendar: (itemId: string, values: { calendar_ics?: string; google_calendar_id?: string }) =>
    request<Integrations>(`/api/integrations/calendar/items/${encodeURIComponent(itemId)}`, json("PUT", values)),

  // Google Calendar
  googleConnectUrl: () => request<{ url: string }>("/api/integrations/google/connect", { auth: "merchant" }),
  googleCalendars: () => request<{ items: GoogleCalendarOption[] }>("/api/integrations/google/calendars", { auth: "merchant" }),
  updateGoogle: (values: { calendar_id?: string; check_busy?: boolean }) =>
    request<Integrations>("/api/integrations/google", json("PATCH", values)),
  disconnectGoogle: () => request<Integrations>("/api/integrations/google", { method: "DELETE", auth: "merchant" }),
};
