import type { ApiSessionResponse, Session } from "./types";

const API_URL = import.meta.env.DEV
  ? "/api"
  : (import.meta.env.VITE_API_URL || "http://localhost:8000/api").replace(/\/$/, "");
const SESSION_KEY = "wayfarer.session";
const imageCache = new Map<string, string | null>();
const imageRequests = new Map<string, Promise<string | null>>();

export function readSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function saveSession(session: Session | null): void {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
}

function expireSession(): void {
  saveSession(null);
  window.dispatchEvent(new Event("wayfarer:session-expired"));
}

async function refreshSession(): Promise<boolean> {
  const session = readSession();
  if (!session?.refresh_token) return false;
  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refresh_token }),
    });
    if (!response.ok) {
      saveSession(null);
      return false;
    }
    const result = (await response.json()) as ApiSessionResponse;
    saveSession(result.session);
    return Boolean(result.session);
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  status: number;
  retryAfter: number | null;
  constructor(message: string, status: number, retryAfter: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === "string") return item;
      if (!item || typeof item !== "object") return null;
      const error = item as { loc?: unknown[]; msg?: unknown };
      const location = Array.isArray(error.loc)
        ? error.loc.filter((part) => typeof part === "string" || typeof part === "number").join(".")
        : "";
      const message = typeof error.msg === "string" ? error.msg : "";
      return location && message ? `${location}: ${message}` : message || null;
    }).filter((message): message is string => Boolean(message));
    return messages.length ? messages.join(" ") : null;
  }
  if (detail && typeof detail === "object") {
    const error = detail as { message?: unknown; msg?: unknown };
    if (typeof error.message === "string") return error.message;
    if (typeof error.msg === "string") return error.msg;
  }
  return null;
}

async function fetchApi(url: string, options: RequestInit): Promise<Response> {
  try {
    return await fetch(url, options);
  } catch (error) {
    if (error instanceof TypeError) {
      const target = API_URL === "/api" ? "the local FastAPI server at http://127.0.0.1:8000" : API_URL;
      throw new ApiError(
        `Can't reach ${target}. Start FastAPI and keep its terminal running.`,
        0,
      );
    }
    throw error;
  }
}

export async function api<T>(path: string, options: RequestInit = {}, canRefresh = true): Promise<T> {
  const session = readSession();
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (session?.access_token) headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetchApi(`${API_URL}${path}`, { ...options, headers });
  const isSessionRequest = ["/auth/signup", "/auth/login", "/auth/refresh"].includes(path);
  if (response.status === 401 && canRefresh && !isSessionRequest) {
    if (await refreshSession()) return api<T>(path, options, false);
    expireSession();
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown };
      const detail = formatApiDetail(payload.detail);
      const topLevelMessage = typeof payload.message === "string" ? payload.message : null;
      if (detail || topLevelMessage) message = detail || topLevelMessage || message;
    } catch {
      // The API may return a non-JSON error response.
    }
    const retryHeader = response.headers.get("Retry-After");
    const retryAfter = retryHeader && Number.isFinite(Number(retryHeader))
      ? Math.max(1, Math.ceil(Number(retryHeader)))
      : null;
    throw new ApiError(message, response.status, retryAfter);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) });
}

async function loadImage(query: string): Promise<string | null> {
  const session = readSession();
  const response = await fetch(`${API_URL}/images?q=${encodeURIComponent(query)}`, {
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
  });
  if (response.status === 401 && await refreshSession()) return loadImage(query);
  if (response.status === 401) expireSession();
  if (response.status === 204) {
    return null;
  }
  if (!response.ok) throw new ApiError("Image could not be loaded.", response.status);
  return URL.createObjectURL(await response.blob());
}

export function getImage(query: string): Promise<string | null> {
  if (imageCache.has(query)) return Promise.resolve(imageCache.get(query) ?? null);
  const pending = imageRequests.get(query);
  if (pending) return pending;
  const request = loadImage(query)
    .then((url) => {
      imageCache.set(query, url);
      return url;
    })
    .finally(() => imageRequests.delete(query));
  imageRequests.set(query, request);
  return request;
}
