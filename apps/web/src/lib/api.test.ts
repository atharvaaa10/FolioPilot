import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiError } from "./api";

describe("apiClient envelope handling", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("unwraps and returns payload data when API returns success envelope", async () => {
    const mockPayload = { status: "ready", database: "healthy", redis: "healthy" };
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        success: true,
        data: mockPayload,
      }),
    } as unknown as Response;

    global.fetch = vi.fn().mockResolvedValue(mockResponse);

    const result = await apiClient<typeof mockPayload>("/api/v1/health/ready");
    expect(result).toEqual(mockPayload);
  });

  it("throws typed ApiError when API returns a standard failure envelope", async () => {
    const mockErrorPayload = {
      code: "SERVICE_UNAVAILABLE",
      message: "One or more dependent services are unavailable",
      details: { database: "unhealthy", redis: "healthy" },
    };
    const mockResponse = {
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        success: false,
        error: mockErrorPayload,
      }),
    } as unknown as Response;

    global.fetch = vi.fn().mockResolvedValue(mockResponse);

    await expect(apiClient("/api/v1/health/ready")).rejects.toThrow(ApiError);

    try {
      await apiClient("/api/v1/health/ready");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe("SERVICE_UNAVAILABLE");
      expect(apiErr.status).toBe(503);
      expect(apiErr.message).toBe("One or more dependent services are unavailable");
      expect(apiErr.details).toEqual({ database: "unhealthy", redis: "healthy" });
    }
  });

  it("throws ApiError with NETWORK_ERROR code on network failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Failed to fetch"));

    await expect(apiClient("/api/v1/health")).rejects.toThrow(ApiError);

    try {
      await apiClient("/api/v1/health");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe("NETWORK_ERROR");
      expect(apiErr.status).toBe(0);
      expect(apiErr.message).toBe("Failed to fetch");
    }
  });
});

