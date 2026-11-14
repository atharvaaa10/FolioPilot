import * as React from "react";
import { renderToString } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ValuationCards } from "@/components/valuation/valuation-cards";
import { AllocationDonut } from "@/components/valuation/allocation-donut";
import { ValueSeriesChart } from "@/components/valuation/value-series-chart";
import valuationResponseFixture from "./fixtures/contract/valuation-response.json";
import valuationSummaryFixture from "./fixtures/contract/valuation-summary.json";
import type { ValuationTotals } from "@/lib/schemas/contract";

describe("Valuation Components SSR Hydration Safety", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
  });

  it("renderToString of ValuationCards produces clean HTML without throwing", () => {
    const totals: ValuationTotals = valuationResponseFixture.totals;
    let html = "";
    expect(() => {
      html = renderToString(<ValuationCards totals={totals} />);
    }).not.toThrow();

    expect(html).toContain("Current Value");
    expect(html).toContain("Cost Basis");
    expect(html).toContain("Unrealized Gain");
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it("renderToString of AllocationDonut renders loading state on server to prevent hydration skew", () => {
    let html = "";
    expect(() => {
      html = renderToString(
        <AllocationDonut items={valuationSummaryFixture.allocation.by_asset_class} />
      );
    }).not.toThrow();

    expect(html).toContain("Loading allocation...");
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it("renderToString of ValueSeriesChart renders loading placeholder on server", () => {
    let html = "";
    expect(() => {
      html = renderToString(
        <ValueSeriesChart
          portfolioId="p-test-1"
          initialPoints={[]}
          title="Value Trend"
        />
      );
    }).not.toThrow();

    expect(html).toContain("Loading chart...");
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it("hydrates ValuationCards on client without errors", () => {
    const totals: ValuationTotals = valuationResponseFixture.totals;
    render(<ValuationCards totals={totals} />);

    expect(screen.getByText("₹9,600.00")).toBeInTheDocument();
    expect(screen.getByText("₹6,400.00")).toBeInTheDocument();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });
});
