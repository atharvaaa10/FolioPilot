import { describe, expect, it } from "vitest";

import {
  formatDateString,
  formatNav,
  getAssetClassBadge,
  getOptionBadge,
  getPlanBadge,
} from "./formatters";

describe("formatters utilities", () => {
  it("formatNav formats numbers and numeric strings to INR currency", () => {
    expect(formatNav(92.7055)).toBe("₹92.7055");
    expect(formatNav("100.5")).toBe("₹100.50");
    expect(formatNav(null)).toBe("—");
    expect(formatNav(undefined)).toBe("—");
    expect(formatNav("invalid")).toBe("—");
  });

  it("formatDateString formats ISO YYYY-MM-DD into calendar string", () => {
    expect(formatDateString("2026-11-06")).toBe("06 Nov 2026");
    expect(formatDateString("2026-01-15")).toBe("15 Jan 2026");
    expect(formatDateString(null)).toBe("—");
    expect(formatDateString("")).toBe("—");
  });

  it("getAssetClassBadge maps all five asset classes correctly", () => {
    expect(getAssetClassBadge("equity").label).toBe("Equity");
    expect(getAssetClassBadge("equity").className).toContain("emerald");

    expect(getAssetClassBadge("debt").label).toBe("Debt");
    expect(getAssetClassBadge("debt").className).toContain("sky");

    expect(getAssetClassBadge("gold").label).toBe("Gold");
    expect(getAssetClassBadge("gold").className).toContain("amber");

    expect(getAssetClassBadge("hybrid").label).toBe("Hybrid");
    expect(getAssetClassBadge("hybrid").className).toContain("purple");

    expect(getAssetClassBadge("other").label).toBe("Other");
    expect(getAssetClassBadge("other").className).toContain("zinc");
  });

  it("getPlanBadge maps plans correctly", () => {
    expect(getPlanBadge("direct").label).toBe("Direct");
    expect(getPlanBadge("regular").label).toBe("Regular");
    expect(getPlanBadge("unknown").label).toBe("Unknown");
  });

  it("getOptionBadge maps options correctly", () => {
    expect(getOptionBadge("growth").label).toBe("Growth");
    expect(getOptionBadge("idcw").label).toBe("IDCW");
    expect(getOptionBadge("unknown").label).toBe("Unknown");
  });
});

