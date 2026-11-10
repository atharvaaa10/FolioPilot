import * as React from "react";
import { renderToString } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SipCard } from "@/components/sips/sip-card";
import { CreateSipDialog } from "@/components/sips/create-sip-dialog";
import { InstallmentsDialog } from "@/components/sips/installments-dialog";
import sipDetailFixture from "./fixtures/contract/sip-detail.json";
import sipInstallmentsFixture from "./fixtures/contract/sip-installments.json";
import { SipDetail } from "@/lib/schemas/contract";

describe("SIP Components SSR hydration & rendering safety", () => {
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
        queries: {
          retry: false,
        },
      },
    });
  }

  it("renderToString of SipCard renders without hydration mismatch or clock leaks", () => {
    const queryClient = createTestQueryClient();
    const sip = sipDetailFixture as unknown as SipDetail;

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <SipCard
          portfolioId={sip.portfolio_id}
          sip={sip}
          onViewInstallments={() => {}}
        />
      </QueryClientProvider>
    );

    expect(html).toContain(sip.fund.name);
    expect(html).toContain(sip.fund.amc);
    expect(html).toContain("Active");
    // Ensure no dynamic live clock time string is rendered on server
    expect(html).not.toMatch(/\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\b/);
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });

  it("renderToString of CreateSipDialog renders without throwing or emitting warnings", () => {
    const queryClient = createTestQueryClient();

    // Radix Dialog renders portals on client side; renderToString should not throw or emit errors
    expect(() => {
      const html = renderToString(
        <QueryClientProvider client={queryClient}>
          <CreateSipDialog
            portfolioId="11111111-1111-1111-1111-111111111111"
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

  it("renders CreateSipDialog on client when open", () => {
    const queryClient = createTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <CreateSipDialog
          portfolioId="11111111-1111-1111-1111-111111111111"
          open={true}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    );

    expect(screen.getByText("Create Systematic Investment Plan (SIP)")).toBeInTheDocument();
    expect(screen.getByLabelText(/Monthly Amount/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Day of Month/i)).toBeInTheDocument();
  });

  it("renders InstallmentsDialog on client with installments fixture data", () => {
    const queryClient = createTestQueryClient();
    const sip = sipDetailFixture as unknown as SipDetail;

    queryClient.setQueryData(
      ["sip_installments", sip.portfolio_id, sip.id, "all", 25],
      sipInstallmentsFixture
    );

    render(
      <QueryClientProvider client={queryClient}>
        <InstallmentsDialog
          portfolioId={sip.portfolio_id}
          sip={sip}
          open={true}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    );

    expect(screen.getByRole("heading", { name: new RegExp(sip.fund.name, "i") })).toBeInTheDocument();
    expect(screen.getAllByText("Executed").length).toBeGreaterThan(0);
  });
});
