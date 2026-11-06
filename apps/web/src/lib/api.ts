/**
 * Typed API Client for FolioPilot Backend Services.
 * Enforces standard response envelope parsing and error handling.
 */

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

/**
 * Extension Point: Phase 1 JWT Token Provider.
 * Later phases will inject access tokens and handle refresh rotation here.
 */
export async function getAccessToken(): Promise<string | null> {
  return null;
}

const DEFAULT_BASE_URL = "http://localhost:8000";

export function getBaseApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || DEFAULT_BASE_URL;
}

/**
 * Standard typed HTTP client wrapper.
 * Unwraps `{ success: true, data: T }` or throws a typed `ApiError`.
 */
export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {},
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

  // Hook for Phase 1 Authentication token attachment
  const token = await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(url, {
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

