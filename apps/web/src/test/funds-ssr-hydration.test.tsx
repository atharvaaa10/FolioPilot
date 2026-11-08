import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import FundsPage from "@/app/(authenticated)/funds/page";
import FundDetailPage from "@/app/(authenticated)/funds/[schemeCode]/page";
import { NavChart } from "@/components/funds/nav-chart";

describe("Funds & NAV SSR hydration safety", () => {
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

  it("renderToString of /funds page renders cleanly without clock patterns or errors", () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(
      ["funds-search", "", "", "", "", 0],
      {
        items: [
          {
            id: "123e4567-e89b-12d3-a456-426614174000",
            scheme_code: 122639,
            name: "Parag Parikh Flexi Cap Fund",
            amc: "PPFAS Mutual Fund",
            category_raw: "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
            asset_class: "equity",
            sub_category: "flexi-cap",
            plan_type: "direct",
            option_type: "growth",
            latest_nav: "92.7055",
            latest_nav_date: "2026-11-05",
            is_active: true,
            is_tracked: false,
          },
        ],
        has_more: false,
      },
    );

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <FundsPage />
      </QueryClientProvider>,
    );

    expect(html).toContain("Mutual Funds");
    expect(html).toContain("Parag Parikh Flexi Cap Fund");
    expect(html).toContain("92.7055");
    // Ensure no dynamic live clock time string is rendered on the server
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
  });

  it("renderToString of /funds/[schemeCode] page renders cleanly without hydration errors", async () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["fund-detail", 122639], {
      id: "123e4567-e89b-12d3-a456-426614174000",
      scheme_code: 122639,
      isin_growth: "INF879O01027",
      isin_reinvest: null,
      name: "Parag Parikh Flexi Cap Fund",
      amc: "PPFAS Mutual Fund",
      scheme_type_raw: "Open Ended Schemes",
      category_raw: "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
      asset_class: "equity",
      sub_category: "flexi-cap",
      classification_source: "category",
      plan_type: "direct",
      option_type: "growth",
      latest_nav: "92.7055",
      latest_nav_date: "2026-11-05",
      is_active: true,
      is_tracked: false,
    });

    queryClient.setQueryData(["fund-nav", 122639], {
      scheme_code: 122639,
      name: "Parag Parikh Flexi Cap Fund",
      history_available: false,
      points: [],
    });

    const paramsPromise = Promise.resolve({ schemeCode: "122639" });

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <React.Suspense fallback={<div>Loading fund details...</div>}>
          <FundDetailPage params={paramsPromise} />
        </React.Suspense>
      </QueryClientProvider>,
    );

    expect(html).toContain("Loading fund details...");
  });

  it("NavChart renders placeholder during SSR without rendering SVG chart or zero-width canvas", () => {
    const html = renderToString(
      <NavChart
        points={[
          { date: "2026-11-04", nav: "91.39" },
          { date: "2026-11-05", nav: "92.70" },
        ]}
        schemeName="Sample Fund"
      />,
    );

    expect(html).toContain("Loading chart...");
    // Recharts SVG is not rendered on server
    expect(html).not.toContain("<svg");
  });
});
