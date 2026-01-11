import type {
  AuthResponse,
  Episode,
  ReferralInfo,
  Title,
  TitleDetail,
  TitleType,
  WatchRequestPayload,
  WatchResolvePayload,
  WatchResolveResponse,
  WatchResponse,
} from "./types";
import { getCurrentInitData, telegramEnv } from "../state/telegramInitData";
import { waitForAuthReady } from "./authGate";

const API_BASE = "/api";
const AUTH_TOKEN_KEY = "kina_auth_token";
let authToken: string | null = null;

const getDevUserId = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("devUserId");
};

export const getAuthToken = (): string | null => {
  if (authToken) {
    return authToken;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const stored = localStorage.getItem(AUTH_TOKEN_KEY);
  authToken = stored;
  return stored;
};

export const setAuthToken = (token: string | null) => {
  authToken = token;
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
};

const getAuthHeaders = (): Record<string, string> => {
  const token = getAuthToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  const devUserId = getDevUserId();
  if (devUserId) {
    return { "X-Dev-User-Id": devUserId };
  }
  return {};
};

export class ApiError extends Error {
  data?: Record<string, unknown> | null;

  constructor(message: string, data?: Record<string, unknown> | null) {
    super(message);
    this.name = "ApiError";
    this.data = data;
  }
}

const apiFetch = async <T>(
  path: string,
  options: RequestInit = {},
  config: { requiresAuth?: boolean; onResponse?: (response: Response) => void } = {},
): Promise<T> => {
  const devUserId = getDevUserId();
  const token = getAuthToken();
  if (config.requiresAuth && !token && !devUserId) {
    const initData = getCurrentInitData();
    if (!initData) {
      throw new Error("auth_missing");
    }
    await waitForAuthReady();
  }
  const headers = new Headers(options.headers);
  const authHeaders = getAuthHeaders();
  Object.entries(authHeaders).forEach(([key, value]) => headers.set(key, value));
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  config.onResponse?.(response);

  if (response.status === 401 || response.status === 403) {
    const errorPayload = (await response.json().catch(() => null)) as
      | Record<string, unknown>
      | null;
    const detail = errorPayload?.detail as string | undefined;
    if (detail && ["token_expired", "token_invalid", "token_missing"].includes(detail)) {
      setAuthToken(null);
    }
    throw new ApiError("auth_error", errorPayload);
  }

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as
      | Record<string, unknown>
      | null;
    const error = (errorPayload?.error as string | undefined) || response.statusText;
    throw new ApiError(error, errorPayload);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
};

export const api = {
  authWebapp: (ref?: string | null) =>
    apiFetch<AuthResponse>("/auth/webapp", {
      method: "POST",
      body: JSON.stringify({
        initData: getCurrentInitData() || null,
        ref: ref || null,
      }),
    }, {
      onResponse: (response) => {
        if (telegramEnv.debugEnabled) {
          console.info("[tg-auth] /api/auth/webapp", response.status);
        }
      },
    }).then((data) => {
      setAuthToken(data.access_token);
      return data;
    }),
  getReferralMe: () => apiFetch<ReferralInfo>("/referral/me"),
  getTop: (type?: TitleType) =>
    apiFetch<Title[]>(`/catalog/top${type ? `?type=${type}` : ""}`),
  search: (query: string, type?: TitleType) => {
    const params = new URLSearchParams();
    params.set("q", query);
    if (type) {
      params.set("type", type);
    }
    return apiFetch<Title[]>(`/catalog/search?${params.toString()}`, {}, {
      requiresAuth: true,
    });
  },
  getTitle: (id: number) => apiFetch<TitleDetail>(`/title/${id}`),
  getEpisodes: (id: number, season: number) =>
    apiFetch<Episode[]>(`/title/${id}/episodes?season=${season}`),
  getFavorites: () => apiFetch<Title[]>("/favorites", {}, { requiresAuth: true }),
  toggleFavorite: (titleId: number) =>
    apiFetch<{ title_id: number; favorited: boolean }>("/favorites/toggle", {
      method: "POST",
      body: JSON.stringify({ title_id: titleId }),
    }, { requiresAuth: true }),
  getSubscriptions: () =>
    apiFetch<{ title_id: number; enabled: boolean }[]>("/subscriptions", {}, {
      requiresAuth: true,
    }),
  toggleSubscription: (titleId: number) =>
    apiFetch<{ title_id: number; enabled: boolean }>("/subscriptions/toggle", {
      method: "POST",
      body: JSON.stringify({ title_id: titleId }),
    }, { requiresAuth: true }),
  watchRequest: (payload: WatchRequestPayload) =>
    apiFetch<WatchResponse>("/watch/request", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  watchResolve: (payload: WatchResolvePayload) =>
    apiFetch<WatchResolveResponse>("/watch/resolve", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  watchDispatch: (variantId: number) =>
    apiFetch<{ queued: boolean }>("/watch/dispatch", {
      method: "POST",
      body: JSON.stringify({ variant_id: variantId }),
    }),
  adsStart: (variantId: number) =>
    apiFetch<{ nonce: string; ttl: number }>("/ads/start", {
      method: "POST",
      body: JSON.stringify({ variant_id: variantId }),
    }),
  adsComplete: (nonce: string) =>
    apiFetch<{ ok: boolean; pass_ttl: number; variant_id: number }>("/ads/complete", {
      method: "POST",
      body: JSON.stringify({ nonce }),
    }),
};

export const authInfo = {
  get initData(): string {
    return getCurrentInitData();
  },
  get devUserId(): string | null {
    return getDevUserId();
  },
  get token(): string | null {
    return getAuthToken();
  },
};
