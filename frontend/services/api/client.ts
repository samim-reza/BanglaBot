/** The fetch wrapper every API module goes through.
 *
 * Requests go to the same origin; `next.config.ts` rewrites `/api/*` to the
 * FastAPI backend. Each call names which credential it needs (`merchant`,
 * `admin`, or `none`) and the wrapper attaches the stored JWT as a bearer
 * header, so no screen has to remember tokens or 401 handling.
 */

import { withBasePath } from "@/lib/paths";

import { adminToken, clearAdminSession, clearMerchantSession, merchantToken } from "./session";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export type AuthScope = "merchant" | "admin" | "none";

export class ApiRequestError extends Error {
  status: number;
  detail: string;
  /** Response headers (e.g. `X-2FA-Required`, `Retry-After`); absent for client-side errors. */
  headers?: Headers;
  /** The parsed JSON error body, for structured details such as `{errors: [{path, message}]}`. */
  body?: unknown;

  constructor(status: number, statusText: string, detail?: string, extra?: { headers?: Headers; body?: unknown }) {
    super(`${status} ${detail || statusText}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail || statusText;
    this.headers = extra?.headers;
    this.body = extra?.body;
  }
}

export function isApiRequestError(error: unknown): error is ApiRequestError {
  return error instanceof ApiRequestError;
}

export function formatApiError(error: unknown, fallback: string): string {
  if (isApiRequestError(error)) return error.detail || fallback;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function redirect(path: string) {
  if (typeof window !== "undefined") window.location.replace(withBasePath(path));
}

/** Bearer header for the given scope, or a redirect to the right login when the
 * session is missing. Throwing instead of sending keeps a signed-out tab from
 * firing a burst of 401s before the redirect lands. */
export function authHeaders(scope: AuthScope): Record<string, string> {
  if (scope === "none") return {};
  const token = scope === "merchant" ? merchantToken() : adminToken();
  if (token) return { Authorization: `Bearer ${token}` };
  if (scope === "merchant") {
    clearMerchantSession();
    redirect("/login");
  } else {
    clearAdminSession();
    redirect("/admin/login");
  }
  throw new ApiRequestError(401, "Unauthorized", "Login required");
}

async function readErrorDetail(response: Response): Promise<{ detail: string; body?: unknown }> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = body?.detail;
    if (typeof detail === "string") return { detail, body };
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc, msg, type}]
      const text = detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : ""))
        .filter(Boolean)
        .join("; ");
      return { detail: text, body };
    }
    if (detail && typeof detail === "object") {
      const structured = detail as { message?: string; errors?: { path?: string; message?: string }[] };
      // Call-flow / provider validation: {errors: [{path, message}]}
      const listed = Array.isArray(structured.errors)
        ? structured.errors.map((e) => [e.path, e.message].filter(Boolean).join(": ")).filter(Boolean).join("; ")
        : "";
      return { detail: String(structured.message ?? "") || listed, body };
    }
    return { detail: "", body };
  }
  return { detail: await response.text().catch(() => "") };
}

export type RequestOptions = RequestInit & { auth?: AuthScope };

/** Perform a request and parse the JSON body. */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await rawRequest(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** Perform a request and hand back the raw Response (for blobs such as recordings). */
export async function rawRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const { auth = "none", headers, ...init } = options;
  const scopedHeaders = authHeaders(auth);
  const sentToken = auth === "merchant" ? merchantToken() : "";
  const send = async (scoped: Record<string, string>) => {
    try {
      return await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: {
          ...(init.body ? { "Content-Type": "application/json" } : {}),
          ...scoped,
          ...headers,
        },
        cache: "no-store",
      });
    } catch {
      throw new Error("Could not connect to the backend API.");
    }
  };
  let response = await send(scopedHeaders);

  // The merchant token was replaced while this call was in flight (password change,
  // "sign out everywhere" revoke the old one on purpose): retry once with the new one.
  if (response.status === 401 && auth === "merchant") {
    const fresh = merchantToken();
    if (fresh && fresh !== sentToken) response = await send({ Authorization: `Bearer ${fresh}` });
  }

  if (!response.ok) {
    const { detail, body } = await readErrorDetail(response);
    // A 401 on an authenticated call means the stored token is dead: drop it and
    // send the user back to sign in. Login POSTs use auth "none", so a wrong
    // password never triggers this.
    if (response.status === 401 && auth === "merchant") {
      clearMerchantSession();
      if (typeof window !== "undefined" && window.location.pathname !== withBasePath("/login")) {
        redirect(detail.toLowerCase().includes("session expired") ? "/login?expired=1" : "/login");
        // Never settle: the page keeps its loading state instead of flashing an error
        // while the browser navigates to sign-in.
        return new Promise<Response>(() => undefined);
      }
    }
    if (response.status === 401 && auth === "admin") {
      clearAdminSession();
      redirect(detail.toLowerCase().includes("session expired") ? "/admin/login?expired=1" : "/admin/login");
    }
    throw new ApiRequestError(response.status, response.statusText, detail, { headers: response.headers, body });
  }
  return response;
}

export function queryString(values: Record<string, string | number | boolean | undefined | null>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    // `false` and `0` are meaningful filter values, so only skip empty/absent ones.
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}
