"use client";

export type ApiError = { code: string; message: string; details?: unknown[] };

let csrfToken = "";
let unauthorizedHandler: (() => void) | null = null;

export function setCsrf(token: string) {
  csrfToken = token;
}
export function getCsrf() {
  return csrfToken;
}
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

export class RequestError extends Error {
  status: number;
  body: ApiError;
  constructor(status: number, body: ApiError) {
    super(body?.message ?? "So'rov bajarilmadi");
    this.status = status;
    this.body = body;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    return data?.error ?? { code: "UNKNOWN", message: data?.detail ?? "Xatolik" };
  } catch {
    return { code: "NETWORK", message: `Server javobi: ${response.status}` };
  }
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (csrfToken && options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401 && unauthorizedHandler) {
    unauthorizedHandler();
    throw new RequestError(401, { code: "UNAUTHENTICATED", message: "Sessiya tugagan" });
  }
  if (response.status === 403 && retry && (await response.clone().text()).includes("CSRF")) {
    const me = await fetch("/api/v1/auth/me", { credentials: "same-origin" });
    if (me.ok) {
      const data = await me.json();
      csrfToken = data.csrf_token;
      return request<T>(path, options, false);
    }
  }
  if (!response.ok) {
    throw new RequestError(response.status, await parseError(response));
  }
  if (response.status === 204) return undefined as T;
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("application/json")) return (await response.json()) as T;
  return (await response.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  async upload<T>(path: string, form: FormData) {
    const headers: Record<string, string> = {};
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(`/api/v1${path}`, {
      method: "POST",
      body: form,
      headers,
      credentials: "same-origin",
    });
    if (!response.ok) throw new RequestError(response.status, await parseError(response));
    return (await response.json()) as T;
  },
  async file(path: string, filename: string) {
    const headers: Record<string, string> = {};
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(`/api/v1${path}`, { headers, credentials: "same-origin" });
    if (!response.ok) throw new RequestError(response.status, await parseError(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.rel = "noopener";
    // D-9: `<a>` DOM'ga qo'shilmasa Safari/Firefox yuklab olishni
    // to'xtatishi mumkin; obekt URL haqiqiy yuklanish tugagandan keyin
    // bekor qilinadi (darhol revoke qilish yuklashni buzadi).
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

export type PageMeta = { page: number; page_size: number; total: number; total_pages: number };
export type Paged<T> = { items: T[]; meta: PageMeta };
