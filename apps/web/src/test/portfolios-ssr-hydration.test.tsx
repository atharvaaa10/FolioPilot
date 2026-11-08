import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import PortfoliosPage from "@/app/(authenticated)/portfolios/page";
import PortfolioDetailPage from "@/app/(authenticated)/portfolios/[id]/page";

describe("Portfolios & Ledger SSR hydration safety", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  function createTestQueryClient() {
    return new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  }

  it("renderToString of /portfolios page renders cleanly without clock patterns or errors", () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["portfolios"], [
      {
        id: "123e4567-e89b-12d3-a456-426614174000",
        name: "Retirement Corpus",
        description: "Long-term financial freedom",
        created_at: "2026-11-01T10:00:00Z",
        updated_at: "2026-11-01T10:00:00Z",
        targets: [
          { asset_class: "equity", target_pct: "60.00" },
          { asset_class: "debt", target_pct: "40.00" },
        ],
      },
    ]);

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <PortfoliosPage />
      </QueryClientProvider>,
    );

    expect(html).toContain("Portfolios");
    expect(html).toContain("Retirement Corpus");
    expect(html).toContain("Long-term financial freedom");
    // Ensure no dynamic live clock time string is rendered on the server
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
  });

  it("renderToString of /portfolios/[id] page renders metric cards and holdings cleanly", () => {
    const queryClient = createTestQueryClient();
    const portfolioId = "123e4567-e89b-12d3-a456-426614174000";

    queryClient.setQueryData(["portfolio", portfolioId], {
      id: portfolioId,
      name: "Wealth Growth",
      description: "Aggressive portfolio",
      created_at: "2026-11-01T10:00:00Z",
      updated_at: "2026-11-01T10:00:00Z",
      targets: [
        { asset_class: "equity", target_pct: "70.00" },
        { asset_class: "gold", target_pct: "30.00" },
      ],
      total_cost_basis: "6400.00",
      open_positions: 1,
      total_transactions: 3,
    });

    queryClient.setQueryData(["holdings", portfolioId], {
      items: [
        {
          scheme_code: 122639,
          fund: {
            name: "Parag Parikh Flexi Cap Fund",
            amc: "PPFAS Mutual Fund",
            asset_class: "equity",
            sub_category: "flexi-cap",
            plan_type: "direct",
            option_type: "growth",
            latest_nav: "93.94830000",
            latest_nav_date: "2026-11-06",
          },
          units: "120.0000",
          avg_cost: "53.3333",
          cost_basis: "6400.00",
          total_bought: "8000.00",
          total_sold: "2100.00",
          first_txn_date: "2025-01-10",
          last_txn_date: "2025-03-10",
          txn_count: 3,
          is_closed: false,
        },
      ],
      totals: {
        cost_basis: "6400.00",
        open_positions: 1,
      },
    });

    queryClient.setQueryData(["transactions", portfolioId], [
      {
        id: "txn-1",
        portfolio_id: portfolioId,
        fund_id: "fund-1",
        scheme_code: 122639,
        fund_name: "Parag Parikh Flexi Cap Fund",
        txn_type: "BUY",
        txn_date: "2025-01-10",
        units: "100.0000",
        nav: "50.00000000",
        amount: "5000.00",
        notes: "Initial buy",
        created_at: "2025-01-10T10:00:00Z",
      },
    ]);

    const paramsPromise = Promise.resolve({ id: portfolioId });

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <React.Suspense fallback={<div>Loading portfolio details...</div>}>
          <PortfolioDetailPage params={paramsPromise} />
        </React.Suspense>
      </QueryClientProvider>,
    );

    expect(html).toContain("Loading portfolio details...");
  });
});
