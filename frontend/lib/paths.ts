export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export function withBasePath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (BASE_PATH && normalized.startsWith(BASE_PATH)) return normalized;
  return `${BASE_PATH}${normalized}`;
}

export function stripBasePath(pathname: string): string {
  if (BASE_PATH && pathname.startsWith(BASE_PATH)) {
    const stripped = pathname.slice(BASE_PATH.length);
    return stripped || "/";
  }
  return pathname;
}

export function assetPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return withBasePath(normalized);
}
