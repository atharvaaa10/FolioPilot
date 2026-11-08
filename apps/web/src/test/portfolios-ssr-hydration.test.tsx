import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import PortfoliosPage from "@/app/(authenticated)/portfolios/page";
import PortfolioDetailPage from "@/app/(authenticated)/portfolios/[id]/page";
import portfolioDetailFixture from "./fixtures/contract/portfolio-detail.json";
import holdingsFixture from "./fixtures/contract/holdings.json";
import transactionsFixture from "./fixtures/contract/transactions.json";

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
        id: portfolioDetailFixture.id,
        name: portfolioDetailFixture.name,
        description: portfolioDetailFixture.description,
        created_at: portfolioDetailFixture.created_at,
        updated_at: portfolioDetailFixture.updated_at,
        targets: portfolioDetailFixture.targets,
      },
    ]);

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <PortfoliosPage />
      </QueryClientProvider>,
    );

    expect(html).toContain("Portfolios");
    expect(html).toContain("Retirement");
    // Ensure no dynamic live clock time string is rendered on the server
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
  });

  it("renderToString of /portfolios/[id] page renders metric cards and holdings cleanly", () => {
    const queryClient = createTestQueryClient();
    const portfolioId = portfolioDetailFixture.id;

    queryClient.setQueryData(["portfolio", portfolioId], portfolioDetailFixture);
    queryClient.setQueryData(["holdings", portfolioId], holdingsFixture);
    queryClient.setQueryData(["transactions", portfolioId], transactionsFixture);

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
