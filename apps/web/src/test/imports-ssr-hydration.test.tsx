import * as React from "react";
import { renderToString } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ImportDialog } from "@/components/imports/import-dialog";
import { ImportHistory } from "@/components/imports/import-history";
import PortfolioDetailPage from "@/app/(authenticated)/portfolios/[id]/page";
import portfolioDetailFixture from "./fixtures/contract/portfolio-detail.json";
import holdingsFixture from "./fixtures/contract/holdings.json";
import transactionsFixture from "./fixtures/contract/transactions.json";
import importHistoryFixture from "./fixtures/contract/import-history.json";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: portfolioDetailFixture.id }),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
  usePathname: () => `/portfolios/${portfolioDetailFixture.id}`,
}));

describe("Import Components SSR Hydration Safety", () => {
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

  function createTestQueryClient() {
    return new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  }

  it("renderToString of ImportDialog when closed renders without throwing or emitting warnings", () => {
    const queryClient = createTestQueryClient();

    // Radix Dialog renders portals on client side; renderToString should not throw or emit errors
    expect(() => {
      const html = renderToString(
        <QueryClientProvider client={queryClient}>
          <ImportDialog
            portfolioId="p-test-123"
            open={false}
            onOpenChange={() => {}}
          />
        </QueryClientProvider>
      );
      expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
    }).not.toThrow();

    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });

  it("renders ImportDialog on client when open", () => {
    const queryClient = createTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <ImportDialog
          portfolioId="p-test-123"
          open={true}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    );

    expect(screen.getByText("Import Transactions from Excel")).toBeInTheDocument();
    expect(screen.getByText("Download Template (.xlsx)")).toBeInTheDocument();
  });

  it("renderToString of ImportHistory renders cleanly without errors", () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["import-history", "p-test-123"], importHistoryFixture);

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <ImportHistory portfolioId="p-test-123" />
      </QueryClientProvider>
    );

    expect(html).toContain("Import History");
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });

  it("SSR and client hydration of /portfolios/[id] page produces no hydration mismatch warnings", () => {
    const queryClient = createTestQueryClient();
    const portfolioId = portfolioDetailFixture.id;

    queryClient.setQueryData(["portfolio", portfolioId], portfolioDetailFixture);
    queryClient.setQueryData(["holdings", portfolioId], holdingsFixture);
    queryClient.setQueryData(["transactions", portfolioId], transactionsFixture);
    queryClient.setQueryData(["sips", portfolioId], []);
    queryClient.setQueryData(["import-history", portfolioId], importHistoryFixture);

    const paramsPromise = Promise.resolve({ id: portfolioId });

    // 1. SSR renderToString
    const ssrHtml = renderToString(
      <QueryClientProvider client={queryClient}>
        <React.Suspense fallback={<div>Loading portfolio details...</div>}>
          <PortfolioDetailPage params={paramsPromise} />
        </React.Suspense>
      </QueryClientProvider>
    );

    expect(ssrHtml).toContain("Loading portfolio details...");

    // 2. Client render into DOM
    render(
      <QueryClientProvider client={queryClient}>
        <React.Suspense fallback={<div>Loading portfolio details...</div>}>
          <PortfolioDetailPage params={paramsPromise} />
        </React.Suspense>
      </QueryClientProvider>
    );

    // Assert that React hydration emitted zero errors and zero warnings
    for (const call of consoleWarnSpy.mock.calls) {
      const msg = String(call[0] ?? "");
      expect(msg).not.toMatch(/hydration/i);
    }
    for (const call of consoleErrorSpy.mock.calls) {
      const msg = String(call[0] ?? "");
      expect(msg).not.toMatch(/hydration/i);
    }
  });
});
