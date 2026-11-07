import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiError, clearAccessToken, getAccessToken, setAccessToken } from "./api";

describe("apiClient refresh token rotation & concurrency", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    clearAccessToken();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    clearAccessToken();
  });

  it("coalesces concurrent requests during token expiration into a single refresh flight", async () => {
    setAccessToken("expired-access-token");
    let refreshCallCount = 0;

    const mockFetch = vi.fn().mockImplementation(async (url: string | URL, options?: RequestInit) => {
      const urlStr = url.toString();

      // Refresh endpoint call
      if (urlStr.endsWith("/api/v1/auth/refresh")) {
        refreshCallCount++;
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            success: true,
            data: { access_token: "fresh-access-token", token_type: "Bearer", expires_in: 900 },
          }),
        } as unknown as Response;
      }

      // First call with expired token
      const authHeader = options?.headers instanceof Headers
        ? options.headers.get("Authorization")
        : (options?.headers as Record<string, string>)?.["Authorization"];

      if (authHeader === "Bearer expired-access-token") {
        return {
          ok: false,
          status: 401,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            success: false,
            error: { code: "TOKEN_EXPIRED", message: "Access token expired" },
          }),
        } as unknown as Response;
      }

      // Retried call with new token
      if (authHeader === "Bearer fresh-access-token") {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            success: true,
            data: { resource: urlStr },
          }),
        } as unknown as Response;
      }

      return {
        ok: false,
        status: 400,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ success: false, error: { code: "BAD_REQUEST", message: "Bad" } }),
      } as unknown as Response;
    });

    global.fetch = mockFetch;

    // Launch 3 concurrent requests simultaneously
    const [res1, res2, res3] = await Promise.all([
      apiClient<{ resource: string }>("/api/v1/users/me"),
      apiClient<{ resource: string }>("/api/v1/portfolio"),
      apiClient<{ resource: string }>("/api/v1/funds"),
    ]);

    expect(res1.resource).toContain("/api/v1/users/me");
    expect(res2.resource).toContain("/api/v1/portfolio");
    expect(res3.resource).toContain("/api/v1/funds");

    // Must have executed exactly 1 refresh network call across all 3 requests
    expect(refreshCallCount).toBe(1);
    expect(getAccessToken()).toBe("fresh-access-token");
  });

  it("clears access token and fails requests when refresh call is rejected", async () => {
    setAccessToken("expired-access-token");

    global.fetch = vi.fn().mockImplementation(async (url: string | URL) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/api/v1/auth/refresh")) {
        return {
          ok: false,
          status: 401,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            success: false,
            error: { code: "REFRESH_TOKEN_REUSED", message: "Family revoked" },
          }),
        } as unknown as Response;
      }

      return {
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          success: false,
          error: { code: "TOKEN_EXPIRED", message: "Expired" },
        }),
      } as unknown as Response;
    });

    await expect(apiClient("/api/v1/users/me")).rejects.toThrow(ApiError);
    expect(getAccessToken()).toBeNull();
  });

  it("does NOT attempt refresh for /api/v1/auth/* endpoints", async () => {
    let refreshTriggered = false;

    global.fetch = vi.fn().mockImplementation(async (url: string | URL) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/api/v1/auth/refresh")) {
        refreshTriggered = true;
      }

      return {
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          success: false,
          error: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" },
        }),
      } as unknown as Response;
    });

    await expect(apiClient("/api/v1/auth/login", { method: "POST" })).rejects.toThrow(ApiError);
    expect(refreshTriggered).toBe(false);
  });
});

