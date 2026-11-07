/**
 * Typed API Client for FolioPilot Backend Services.
 * Enforces standard response envelope parsing, credentials inclusion,
 * automatic token attachment, and single-flight refresh token rotation.
 */

import { clearAccessToken, getAccessToken, setAccessToken } from "./auth-token";

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiSuccessResponse<T> {
  success: true;
  data: T;
  error?: null;
}

export interface ApiErrorResponse {
  success: false;
  data?: null;
  error: ApiErrorPayload;
}

export type ApiResponse<T> = ApiSuccessResponse<T> | ApiErrorResponse;

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly details?: unknown;

  constructor(message: string, code: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

const DEFAULT_BASE_URL = "http://localhost:8000";

export function getBaseApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || DEFAULT_BASE_URL;
}

// Single-flight refresh token lock
let refreshPromise: Promise<string | null> | null = null;

/**
 * Execute single-flight refresh against POST /api/v1/auth/refresh.
 * Concurrent requests await the identical active promise.
 */
export async function requestTokenRefresh(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const baseUrl = getBaseApiUrl();
      const response = await fetch(`${baseUrl}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        clearAccessToken();
        return null;
      }

      const payload = (await response.json()) as ApiResponse<{ access_token: string }>;
      if (payload.success && payload.data?.access_token) {
        const newToken = payload.data.access_token;
        setAccessToken(newToken);
        return newToken;
      }

      clearAccessToken();
      return null;
    } catch {
      clearAccessToken();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

/**
 * Standard typed HTTP client wrapper.
 * Unwraps `{ success: true, data: T }` or throws a typed `ApiError`.
 */
export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {},
  isRetry = false,
): Promise<T> {
  const baseUrl = getBaseApiUrl();
  const normalizedPath = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${normalizedPath}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      credentials: "include",
      ...options,
      headers,
    });
  } catch (networkError) {
    throw new ApiError(
      networkError instanceof Error ? networkError.message : "Network connection failed",
      "NETWORK_ERROR",
      0,
    );
  }

  let responseJson: ApiResponse<T> | null = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      responseJson = (await response.json()) as ApiResponse<T>;
    } catch {
      responseJson = null;
    }
  }

  // Handle expired token on non-auth endpoints by attempting a single refresh
  const isAuthEndpoint = normalizedPath.includes("/auth/");
  const hasTokenExpiredError =
    responseJson !== null &&
    !responseJson.success &&
    responseJson.error?.code === "TOKEN_EXPIRED";

  const isTokenExpired = response.status === 401 || hasTokenExpiredError;

  if (!isRetry && !isAuthEndpoint && isTokenExpired) {
    const refreshedToken = await requestTokenRefresh();
    if (refreshedToken) {
      // Retry original request once with fresh token
      return apiClient<T>(endpoint, options, true);
    }

    // Refresh failed or revoked: clear access token and redirect if in browser
    clearAccessToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      try {
        window.location.href = `/login?next=${next}`;
      } catch {
        // Suppress jsdom navigation error in unit test environment
      }
    }
  }

  if (!response.ok || (responseJson && !responseJson.success)) {
    if (responseJson && !responseJson.success && responseJson.error) {
      throw new ApiError(
        responseJson.error.message,
        responseJson.error.code,
        response.status,
        responseJson.error.details,
      );
    }

    throw new ApiError(
      response.statusText || `HTTP error ${response.status}`,
      `HTTP_${response.status}`,
      response.status,
    );
  }

  if (responseJson && responseJson.success) {
    return responseJson.data;
  }

  // Fallback if HTTP 200 returned without standard JSON body
  return (responseJson as unknown as T) || ({} as T);
}

export { clearAccessToken, getAccessToken, setAccessToken };
