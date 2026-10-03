/** The account's call & chat log. */

import { queryString, rawRequest, request } from "./client";
import type { CallChannel, CallLog, Page } from "./types";

export type CallListParams = { page?: number; page_size?: number; direction?: CallChannel | ""; outcome?: string };

export const callsApi = {
  list: (params: CallListParams = {}) => request<Page<CallLog>>(`/api/calls${queryString(params)}`, { auth: "merchant" }),
  recordingObjectUrl: async (logId: string) => {
    const response = await rawRequest(`/api/calls/${encodeURIComponent(logId)}/recording`, { auth: "merchant" });
    return URL.createObjectURL(await response.blob());
  },
};
