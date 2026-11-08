import { describe, expect, it } from "vitest";
import { evaluateTargets } from "./targets";

describe("evaluateTargets", () => {
  it("sums 33.33 + 33.33 + 33.34 to exactly 100.00 and enables save", () => {
    const targets = [
      { asset_class: "equity", target_pct: "33.33" },
      { asset_class: "debt", target_pct: "33.33" },
      { asset_class: "gold", target_pct: "33.34" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.totalPct).toBe("100.00");
    expect(summary.remainingPct).toBe("0.00");
    expect(summary.isExactHundred).toBe(true);
    expect(summary.isValid).toBe(true);
    expect(summary.canSave).toBe(true);
    expect(summary.errors).toHaveLength(0);
    expect(summary.generalError).toBeNull();
  });

  it("handles standard 60 / 30 / 10 allocation", () => {
    const targets = [
      { asset_class: "equity", target_pct: "60" },
      { asset_class: "debt", target_pct: "30" },
      { asset_class: "gold", target_pct: "10" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.totalPct).toBe("100.00");
    expect(summary.isExactHundred).toBe(true);
    expect(summary.canSave).toBe(true);
  });

  it("gates save when sum is not 100.00 (e.g. 33.33 + 33.33 + 33.33 = 99.99)", () => {
    const targets = [
      { asset_class: "equity", target_pct: "33.33" },
      { asset_class: "debt", target_pct: "33.33" },
      { asset_class: "gold", target_pct: "33.33" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.totalPct).toBe("99.99");
    expect(summary.remainingPct).toBe("0.01");
    expect(summary.isExactHundred).toBe(false);
    expect(summary.canSave).toBe(false);
    expect(summary.generalError).toContain("Allocations sum to 99.99%");
  });

  it("gates save when sum exceeds 100.00", () => {
    const targets = [
      { asset_class: "equity", target_pct: "70" },
      { asset_class: "debt", target_pct: "40" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.totalPct).toBe("110.00");
    expect(summary.canSave).toBe(false);
    expect(summary.generalError).toContain("10.00% over");
  });

  it("rejects duplicate asset classes", () => {
    const targets = [
      { asset_class: "equity", target_pct: "50" },
      { asset_class: "equity", target_pct: "50" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.canSave).toBe(false);
    expect(summary.errors.some((e) => e.message.includes("Duplicate asset class"))).toBe(true);
  });

  it("rejects more than 5 rows", () => {
    const targets = [
      { asset_class: "equity", target_pct: "20" },
      { asset_class: "debt", target_pct: "20" },
      { asset_class: "hybrid", target_pct: "20" },
      { asset_class: "gold", target_pct: "20" },
      { asset_class: "other", target_pct: "10" },
      { asset_class: "other", target_pct: "10" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.canSave).toBe(false);
    expect(summary.generalError).toContain("Cannot configure more than 5");
  });

  it("rejects decimal precision exceeding 2 places", () => {
    const targets = [
      { asset_class: "equity", target_pct: "50.125" },
      { asset_class: "debt", target_pct: "49.875" },
    ];
    const summary = evaluateTargets(targets);

    expect(summary.canSave).toBe(false);
    expect(summary.errors.some((e) => e.message.includes("Maximum 2 decimal places"))).toBe(true);
  });

  it("allows empty targets (clearing allocations)", () => {
    const summary = evaluateTargets([]);
    expect(summary.isValid).toBe(true);
    expect(summary.canSave).toBe(true);
    expect(summary.totalPct).toBe("0.00");
  });
});

