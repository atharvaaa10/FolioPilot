import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import FundsPage from "@/app/(authenticated)/funds/page";
import FundDetailPage from "@/app/(authenticated)/funds/[schemeCode]/page";
import { NavChart } from "@/components/funds/nav-chart";
import fundsSearchFixture from "./fixtures/contract/funds-search.json";
import fundDetailFixture from "./fixtures/contract/fund-detail.json";
import navHistoryFixture from "./fixtures/contract/nav-history.json";

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
      fundsSearchFixture,
    );

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <FundsPage />
      </QueryClientProvider>,
    );

    expect(html).toContain("Mutual Funds");
    expect(html).toContain("Parag Parikh Flexi Cap Fund");
    expect(html).toContain("33.84");
    // Ensure no dynamic live clock time string is rendered on the server
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
  });

  it("renderToString of /funds/[schemeCode] page renders cleanly without hydration errors", async () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["fund-detail", 122639], fundDetailFixture);
    queryClient.setQueryData(["fund-nav", 122639], navHistoryFixture);

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

  it("renderToString of NavChart component renders cleanly", () => {
    const points = [
      { date: "2026-11-01", nav: "92.1000" },
      { date: "2026-11-02", nav: "92.3500" },
      { date: "2026-11-03", nav: "92.8000" },
    ];

    const html = renderToString(
      <NavChart points={points} schemeName="Test Fund" />,
    );

    expect(html).toContain("Loading chart...");
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
  });
});
