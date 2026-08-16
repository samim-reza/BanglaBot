const TOKEN_KEY = "banglabot_token";
const ROLE_KEY = "banglabot_role";
const NAME_KEY = "banglabot_name";

export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  get role() { return localStorage.getItem(ROLE_KEY); },
  get name() { return localStorage.getItem(NAME_KEY); },
  save(token: string, role: string, name: string) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(ROLE_KEY, role);
    localStorage.setItem(NAME_KEY, name);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(NAME_KEY);
  },
};

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown } = {}
): Promise<T> {
  const hadToken = !!auth.token;
  const res = await fetch(path, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  // Only a 401 on a request that carried a token means the session expired —
  // a 401 from the login endpoints must surface its own error message.
  if (res.status === 401 && hadToken) {
    auth.clear();
    window.location.href = "/login";
    throw new Error("লগইন সেশন শেষ হয়েছে");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = (data as { detail?: unknown }).detail;
    let message: string;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc, msg, ...}, ...]
      message = detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          [(d.loc ?? []).slice(1).join("."), d.msg].filter(Boolean).join(": ")
        )
        .join("; ") || `ত্রুটি (${res.status})`;
    } else {
      message =
        (detail as { message?: string } | null | undefined)?.message ?? `ত্রুটি (${res.status})`;
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Fetch a binary resource (e.g. a call recording) with the auth header. */
export async function fetchBlob(path: string): Promise<Blob> {
  const res = await fetch(path, {
    headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = (data as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `ত্রুটি (${res.status})`);
  }
  return res.blob();
}
