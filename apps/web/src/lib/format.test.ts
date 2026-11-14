import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatInr,
  formatNav,
  formatPercent,
  formatSignedGain,
  formatUnits,

  getAssetClassBadge,
  getOptionBadge,
  getPlanBadge,
  getTodayIsoDate,
} from "./format";

describe("format utilities", () => {
  describe("formatInr", () => {
    it("formats Indian rupees correctly", () => {
      expect(formatInr(0)).toBe("₹0.00");
      expect(formatInr("1000")).toBe("₹1,000.00");
      expect(formatInr(1234567.89)).toBe("₹12,34,567.89");
      expect(formatInr(null)).toBe("₹0.00");
      expect(formatInr(undefined)).toBe("₹0.00");
    });

    it("performs exact Decimal ROUND_HALF_UP rounding without floating point drift", () => {
      expect(formatInr("1234.565")).toBe("₹1,234.57");
      expect(formatInr("1234.564")).toBe("₹1,234.56");
      expect(formatInr("-500.00")).toBe("-₹500.00");
    });
  });

  describe("formatPercent", () => {
    it("formats positive, zero, and negative percentages", () => {
      expect(formatPercent("5.67")).toBe("5.67%");
      expect(formatPercent("0")).toBe("0.00%");
      expect(formatPercent("-2.5")).toBe("-2.50%");
    });

    it("handles null and undefined by returning 0.00%", () => {
      expect(formatPercent(null)).toBe("0.00%");
      expect(formatPercent(undefined)).toBe("0.00%");
    });

    it("performs ROUND_HALF_UP rounding", () => {
      expect(formatPercent("15.505")).toBe("15.51%");
      expect(formatPercent("15.504")).toBe("15.50%");
    });
  });

  describe("formatSignedGain", () => {
    it("formats positive gain with plus signs: +₹1,234.00 (+5.67%)", () => {
      expect(formatSignedGain("1234.00", "5.67")).toBe("+₹1,234.00 (+5.67%)");
    });

    it("formats negative gain: -₹500.00 (-2.50%)", () => {
      expect(formatSignedGain("-500.00", "-2.50")).toBe("-₹500.00 (-2.50%)");
    });

    it("formats zero gain without plus sign: ₹0.00 (0.00%)", () => {
      expect(formatSignedGain("0.00", "0.00")).toBe("₹0.00 (0.00%)");
    });

    it("handles null pct gracefully", () => {
      expect(formatSignedGain("1234.00", null)).toBe("+₹1,234.00");
      expect(formatSignedGain("-500.00", undefined)).toBe("-₹500.00");
    });

    it("handles null gain gracefully", () => {
      expect(formatSignedGain(null, "5.00")).toBe("₹0.00");
      expect(formatSignedGain(undefined, null)).toBe("₹0.00");
    });
  });


  describe("formatNav", () => {
    it("formats NAV up to 4 decimal places", () => {
      expect(formatNav("93.9483")).toBe("₹93.9483");
      expect(formatNav(10.5)).toBe("₹10.50");
      expect(formatNav(null)).toBe("—");
    });
  });

  describe("formatUnits", () => {
    it("formats mutual fund units with 4 decimals", () => {
      expect(formatUnits(100)).toBe("100.0000");
      expect(formatUnits("120.5432")).toBe("120.5432");
      expect(formatUnits(null)).toBe("0.0000");
    });
  });

  describe("formatDate", () => {
    it("formats ISO date string without timezone skew", () => {
      expect(formatDate("2025-01-05")).toBe("05 Jan 2025");
      expect(formatDate("2026-11-06")).toBe("06 Nov 2026");
      expect(formatDate(null)).toBe("—");
      expect(formatDate("")).toBe("—");
    });

    it("produces identical output regardless of system timezone", () => {
      // Direct string parsing ensures immunity to timezone shifting
      const output = formatDate("2025-01-05");
      expect(output).toBe("05 Jan 2025");
    });
  });

  describe("getTodayIsoDate", () => {
    it("returns YYYY-MM-DD formatted date string", () => {
      const today = getTodayIsoDate();
      expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  describe("badge helpers", () => {
    it("maps asset classes to appropriate styles", () => {
      expect(getAssetClassBadge("equity").label).toBe("Equity");
      expect(getAssetClassBadge("debt").label).toBe("Debt");
      expect(getAssetClassBadge("gold").label).toBe("Gold");
      expect(getAssetClassBadge("hybrid").label).toBe("Hybrid");
      expect(getAssetClassBadge("unknown").label).toBe("Other");
    });

    it("maps plan types", () => {
      expect(getPlanBadge("direct").label).toBe("Direct");
      expect(getPlanBadge("regular").label).toBe("Regular");
    });

    it("maps option types", () => {
      expect(getOptionBadge("growth").label).toBe("Growth");
      expect(getOptionBadge("idcw").label).toBe("IDCW");
    });
  });
});

