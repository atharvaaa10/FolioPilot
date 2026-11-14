import * as React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ValuationCards, formatXirrPercent, getXirrMessage } from "@/components/valuation/valuation-cards";
import { formatSignedGain, formatInr } from "@/lib/format";
import type { ValuationTotals, XirrResult } from "@/lib/schemas/contract";
import valuationSummaryFixture from "./fixtures/contract/valuation-summary.json";
import valuationResponseFixture from "./fixtures/contract/valuation-response.json";

describe("Valuation UI Components and Helpers", () => {
  describe("XIRR Helpers", () => {
    it("maps reasons to clear user-facing messages", () => {
      const baseResult: XirrResult = {
        rate: null,
        reason: "NO_TRANSACTIONS",
        short_period: false,
        ambiguous: false,
        flows_count: 0,
        first_flow_date: null,
        last_flow_date: null,
        excluded_funds: 0,
      };

      expect(getXirrMessage({ ...baseResult, reason: "NO_TRANSACTIONS" })).toBe(
        "No transactions in scope."
      );
      expect(getXirrMessage({ ...baseResult, reason: "NO_NAV_DATA" })).toBe(
        "No live NAV data available for open positions."
      );
      expect(getXirrMessage({ ...baseResult, reason: "INSUFFICIENT_FLOWS" })).toBe(
        "At least two distinct cash flow dates with inflows and outflows required."
      );
      expect(getXirrMessage({ ...baseResult, reason: "PERIOD_TOO_SHORT" })).toBe(
        "Investment period is under 30 days. XIRR is not meaningful."
      );
      expect(getXirrMessage({ ...baseResult, reason: "NO_SOLUTION" })).toBe(
        "No valid mathematical solution found for cash flows."
      );
    });

    it("formats positive rates as percentages with 2 decimals", () => {
      expect(formatXirrPercent("0.100000")).toBe("+10.00%");
      expect(formatXirrPercent("-0.052000")).toBe("-5.20%");
      expect(formatXirrPercent(null)).toBe("—");
      expect(formatXirrPercent(undefined)).toBe("—");
    });
  });

  describe("ValuationCards", () => {
    it("renders valuation totals correctly", () => {
      const totals: ValuationTotals = {
        cost_basis: "6400.00",
        current_value: "9600.00",
        unrealized_gain: "3200.00",
        unrealized_gain_pct: "50.00",
        realized_gain: "500.00",
        total_gain: "3700.00",
        open_positions: 1,
        fallback_positions: 0,
        stale_positions: 0,
        xirr: {
          rate: "0.100000",
          reason: null,
          short_period: false,
          ambiguous: false,
          flows_count: 4,
          first_flow_date: "2024-01-15",
          last_flow_date: "2026-11-14",
          excluded_funds: 0,
        },
      };

      render(<ValuationCards totals={totals} />);

      expect(screen.getByText("Current Value")).toBeInTheDocument();
      expect(screen.getByText("Cost Basis")).toBeInTheDocument();
      expect(screen.getByText("Unrealized Gain")).toBeInTheDocument();
      expect(screen.getByText("Realized Gain")).toBeInTheDocument();
      expect(screen.getByText("XIRR")).toBeInTheDocument();

      expect(screen.getByText("₹9,600.00")).toBeInTheDocument();
      expect(screen.getByText("₹6,400.00")).toBeInTheDocument();
      expect(screen.getByText("+₹3,200.00 (+50.00%)")).toBeInTheDocument();
      expect(screen.getByText("₹500.00")).toBeInTheDocument();
      expect(screen.getByText("+10.00%")).toBeInTheDocument();
    });
  });

  describe("Dashboard & Portfolio Totals Consistency", () => {
    it("renders identical text for summary portfolio row and portfolio valuation totals from the same fixture", () => {
      const summaryPortfolio = valuationSummaryFixture.portfolios[0]!;
      const portfolioTotals = valuationResponseFixture.totals;

      // Both must match character-for-character
      expect(formatInr(summaryPortfolio.current_value)).toBe(
        formatInr(portfolioTotals.current_value)
      );
      expect(formatInr(summaryPortfolio.cost_basis)).toBe(
        formatInr(portfolioTotals.cost_basis)
      );
      expect(
        formatSignedGain(
          summaryPortfolio.unrealized_gain,
          summaryPortfolio.unrealized_gain_pct
        )
      ).toBe(
        formatSignedGain(
          portfolioTotals.unrealized_gain,
          portfolioTotals.unrealized_gain_pct
        )
      );
      expect(formatInr(summaryPortfolio.realized_gain)).toBe(
        formatInr(portfolioTotals.realized_gain)
      );
      expect(formatXirrPercent(summaryPortfolio.xirr.rate)).toBe(
        formatXirrPercent(portfolioTotals.xirr.rate)
      );
    });
  });
});
