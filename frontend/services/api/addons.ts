/** The add-on shop and the account's chat channels (WhatsApp, Messenger). */

import { request } from "./client";
import type { AddonShop, ChannelsView } from "./types";

export const addonsApi = {
  shop: () => request<AddonShop>("/api/addons", { auth: "merchant" }),
  /** No online payment yet: the request goes to the platform admin, who turns it on. */
  request: (addon: string, quantity = 1, note = "") =>
    request<AddonShop>("/api/addons/requests", { method: "POST", auth: "merchant", body: JSON.stringify({ addon, quantity, note }) }),
  cancelRequest: (id: string) =>
    request<AddonShop>(`/api/addons/requests/${encodeURIComponent(id)}`, { method: "DELETE", auth: "merchant" }),
};

export const channelsApi = {
  get: () => request<ChannelsView>("/api/channels", { auth: "merchant" }),
  connectMessenger: (page_id: string, page_token: string) =>
    request<ChannelsView>("/api/channels/messenger", { method: "PUT", auth: "merchant", body: JSON.stringify({ page_id, page_token }) }),
  disconnectMessenger: () => request<ChannelsView>("/api/channels/messenger", { method: "DELETE", auth: "merchant" }),
};
