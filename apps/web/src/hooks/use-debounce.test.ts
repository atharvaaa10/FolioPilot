import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDebounce } from "./use-debounce";

describe("useDebounce hook", () => {
  it("returns initial value immediately", () => {
    const { result } = renderHook(() => useDebounce("hello", 300));
    expect(result.current).toBe("hello");
  });

  it("updates value only after specified delay", () => {
    vi.useFakeTimers();

    const { result, rerender } = renderHook(
      ({ val, delay }) => useDebounce(val, delay),
      {
        initialProps: { val: "initial", delay: 300 },
      },
    );

    expect(result.current).toBe("initial");

    // Change value
    rerender({ val: "changed", delay: 300 });
    expect(result.current).toBe("initial");

    // Fast-forward 150ms (not yet debounced)
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe("initial");

    // Fast-forward past 300ms
    act(() => {
      vi.advanceTimersByTime(160);
    });
    expect(result.current).toBe("changed");

    vi.useRealTimers();
  });
});

