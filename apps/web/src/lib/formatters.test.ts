import { describe, expect, it } from "vitest";

import {
  formatCurrency,
  formatDateString,
  formatGainLoss,
  formatNav,
  formatUnits,
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

  it("formatCurrency formats numbers into INR currency with 2 decimals", () => {
    expect(formatCurrency(1234567.89)).toBe("₹12,34,567.89");
    expect(formatCurrency("5000")).toBe("₹5,000.00");
    expect(formatCurrency(null)).toBe("₹0.00");
  });

  it("formatUnits formats units with up to 4 decimal places", () => {
    expect(formatUnits(1234.5678)).toBe("1,234.5678");
    expect(formatUnits("100")).toBe("100.00");
    expect(formatUnits(null)).toBe("0.0000");
  });

  it("formatGainLoss handles positive, negative, and zero values", () => {
    const pos = formatGainLoss("1500.50");
    expect(pos.formatted).toBe("+₹1,500.50");
    expect(pos.isPositive).toBe(true);

    const neg = formatGainLoss(-500.25);
    expect(neg.formatted).toBe("-₹500.25");
    expect(neg.isNegative).toBe(true);

    const zero = formatGainLoss("0");
    expect(zero.formatted).toBe("₹0.00");
    expect(zero.isPositive).toBe(false);
    expect(zero.isNegative).toBe(false);
  });
});

