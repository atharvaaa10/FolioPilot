import { describe, expect, it, vi } from "vitest";

import { pollNavHistory } from "@/lib/nav-polling";

describe("NAV history polling logic", () => {
  it("resolves successfully when checkFn returns true", async () => {
    let callCount = 0;
    const checkFn = vi.fn().mockImplementation(async () => {
      callCount += 1;
      return callCount >= 3;
    });

    const attempts: number[] = [];
    const result = await pollNavHistory({
      intervalMs: 10,
      maxDurationMs: 1000,
      checkFn,
      onAttempt: (att) => attempts.push(att),
    });

    expect(result).toBe(true);
    expect(callCount).toBe(3);
    expect(attempts).toEqual([1, 2, 3]);
  });

  it("times out when history is not available within maxDurationMs", async () => {
    const checkFn = vi.fn().mockResolvedValue(false);

    await expect(
      pollNavHistory({
        intervalMs: 20,
        maxDurationMs: 60,
        checkFn,
      }),
    ).rejects.toThrow("Historical data fetch timed out. Please try again later.");
  });

  it("propagates unexpected checkFn errors immediately", async () => {
    const checkFn = vi.fn().mockRejectedValue(new Error("Network failure"));

    await expect(
      pollNavHistory({
        intervalMs: 10,
        maxDurationMs: 500,
        checkFn,
      }),
    ).rejects.toThrow("Network failure");
  });
});

