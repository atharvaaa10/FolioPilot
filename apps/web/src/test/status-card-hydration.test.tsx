import * as React from "react";
import { act } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HomePage from "@/app/page";
import { LocalTime } from "@/components/ui/local-time";

describe("Status card SSR & hydration safety", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let activeClients: QueryClient[] = [];

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    activeClients.forEach((c) => c.clear());
    activeClients = [];
    consoleErrorSpy.mockRestore();
    document.body.innerHTML = "";
  });

  function createTestQueryClient() {
    const client = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchOnWindowFocus: false,
          staleTime: Infinity,
        },
      },
    });
    activeClients.push(client);
    return client;
  }

  it("renderToString of HomePage status card renders placeholder and no clock pattern", () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["health-ready"], {
      status: "ready",
      database: "healthy",
      redis: "healthy",
    });

    const html = renderToString(
      <QueryClientProvider client={queryClient}>
        <HomePage />
      </QueryClientProvider>,
    );

    expect(html).toContain("Last probed:");
    expect(html).toContain("—");
    // Ensure no clock-like time string (e.g., 04:09:12 or 9:39 AM) is rendered during SSR
    expect(html).not.toMatch(/Last probed:.*?\d{1,2}:\d{2}/);
  });

  it("hydrates HomePage without any React hydration console errors", () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["health-ready"], {
      status: "ready",
      database: "healthy",
      redis: "healthy",
    });

    const ui = (
      <QueryClientProvider client={queryClient}>
        <HomePage />
      </QueryClientProvider>
    );

    const serverHtml = renderToString(ui);

    const container = document.createElement("div");
    document.body.appendChild(container);
    container.innerHTML = serverHtml;

    act(() => {
      hydrateRoot(container, ui);
    });

    const hydrationErrors = consoleErrorSpy.mock.calls
      .map((call) => call.map((arg) => (typeof arg === "string" ? arg : "")).join(" "))
      .filter(
        (msg) =>
          msg.toLowerCase().includes("hydration") ||
          msg.toLowerCase().includes("did not match") ||
          msg.toLowerCase().includes("server-rendered html"),
      );

    expect(hydrationErrors).toHaveLength(0);
  });

  it("hydrates LocalTime cleanly even when timezone/timestamps differ across boundaries", () => {
    const fixedTimestamp = 1700000000000;
    const ui = <LocalTime timestamp={fixedTimestamp} />;

    const serverHtml = renderToString(ui);
    expect(serverHtml).toContain("—");
    expect(serverHtml).not.toMatch(/\d{1,2}:\d{2}/);

    const container = document.createElement("div");
    document.body.appendChild(container);
    container.innerHTML = serverHtml;

    // Simulate different timezone context on client
    const originalTZ = process.env.TZ;
    process.env.TZ = "Asia/Kolkata";

    try {
      act(() => {
        hydrateRoot(container, ui);
      });

      const hydrationErrors = consoleErrorSpy.mock.calls
        .map((call) => call.map((arg) => (typeof arg === "string" ? arg : "")).join(" "))
        .filter(
          (msg) =>
            msg.toLowerCase().includes("hydration") ||
            msg.toLowerCase().includes("did not match"),
        );

      expect(hydrationErrors).toHaveLength(0);
    } finally {
      process.env.TZ = originalTZ;
    }
  });
});

