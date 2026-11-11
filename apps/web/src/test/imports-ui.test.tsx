import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ImportDialog } from "@/components/imports/import-dialog";
import { ImportHistory } from "@/components/imports/import-history";
import * as importsApi from "@/lib/imports-api";
import importSummaryFixture from "./fixtures/contract/import-summary.json";
import importRowsFixture from "./fixtures/contract/import-rows.json";
import type { ImportRow, ImportSummary, ImportUploadResponse } from "@/lib/schemas/contract";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe("ImportDialog & ImportHistory UI Component Tests", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders upload dropzone and download template button in initial state", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ImportDialog
          portfolioId="p-123"
          open={true}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    );

    expect(screen.getByText("Import Transactions from Excel")).toBeDefined();
    expect(
      screen.getByText(/Upload an Excel \(\.xlsx\) file to preview, resolve duplicate transactions/i)
    ).toBeDefined();
    expect(screen.getByText("Download Template (.xlsx)")).toBeDefined();
    expect(screen.getByText(/Click to select or drag and drop your file here/i)).toBeDefined();
  });

  it("calls downloadTemplateBlob when download template button is clicked", async () => {
    const downloadSpy = vi.spyOn(importsApi, "downloadTemplateBlob").mockResolvedValue(
      new Blob(["mock-xlsx-data"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      })
    );

    const createObjectURLSpy = vi.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURLSpy = vi.fn();
    window.URL.createObjectURL = createObjectURLSpy;
    window.URL.revokeObjectURL = revokeObjectURLSpy;

    render(
      <QueryClientProvider client={queryClient}>
        <ImportDialog
          portfolioId="p-123"
          open={true}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    );

    const downloadBtn = screen.getByText("Download Template (.xlsx)");
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(downloadSpy).toHaveBeenCalledTimes(1);
      expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    });
  });

  it("handles upload transition to preview, shows badges, and disables commit button if errors exist", async () => {
    const mockSummaryWithErrors: ImportSummary = {
      ...(importSummaryFixture as unknown as ImportSummary),
      rows_total: 3,
      rows_ok: 1,
      rows_warning: 0,
      rows_duplicate: 1,
      rows_error: 1,
      will_import: 1,
      blocking_errors: [],
    };

    const mockRows: ImportRow[] = [
      {
        row_number: 2,
        status: "ok",
        fund_name_in_file: "Parag Parikh Flexi Cap Fund",
        txn_type: "buy",
        txn_date: "2025-01-15",
        units: "100.000",
        nav: "50.0000",
        amount: "5000.00",
        notes: "Valid row",
        raw: {},
        messages: [],
      },
      {
        row_number: 3,
        status: "error",
        fund_name_in_file: "Unknown Fund",
        txn_type: "buy",
        txn_date: "2025-01-16",
        units: "10.000",
        nav: "10.0000",
        amount: "100.00",
        notes: "<img src=x onerror=alert(1)>",
        raw: {},
        messages: [
          {
            level: "error",
            code: "SCHEME_NOT_FOUND",
            message: "Fund identifier could not be resolved",
          },
        ],
      },
      {
        row_number: 4,
        status: "duplicate",
        fund_name_in_file: "Parag Parikh Flexi Cap Fund",
        txn_type: "buy",
        txn_date: "2025-01-15",
        units: "100.000",
        nav: "50.0000",
        amount: "5000.00",
        notes: '=HYPERLINK("http://malicious.com", "Click Me")',
        raw: {},
        messages: [
          {
            level: "info",
            code: "DUPLICATE_IN_LEDGER",
            message: "Matches existing transaction in ledger",
          },
        ],
      },
    ];

    const mockUploadResponse: ImportUploadResponse = {
      import: mockSummaryWithErrors,
      rows: mockRows,
    };

    vi.spyOn(importsApi, "uploadImportFile").mockResolvedValue(mockUploadResponse);

    render(
      <QueryClientProvider client={queryClient}>
        <ImportDialog
          portfolioId="p-123"
          open={true}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    );

    // Simulate file input change
    const fileInput = document.getElementById("file-input") as HTMLInputElement;
    const testFile = new File(["dummy content"], "transactions.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    fireEvent.change(fileInput, { target: { files: [testFile] } });

    // Click Analyze & Preview
    const analyzeBtn = screen.getByRole("button", { name: /Analyze & Preview/i });
    expect(analyzeBtn).toBeDefined();
    fireEvent.click(analyzeBtn);

    // Should transition to preview
    await waitFor(() => {
      expect(screen.getByText("Total Rows")).toBeDefined();
    });

    // Check summary metrics in badges/cards
    expect(screen.getByText("Errors")).toBeDefined();
    expect(screen.getByText("Duplicates")).toBeDefined();
    expect(screen.getByText("Will Import")).toBeDefined();

    // Check commit button is disabled because errors exist and skipInvalid is false
    const commitBtn = screen.getByRole("button", { name: /Import 1 Transaction/i }) as HTMLButtonElement;
    expect(commitBtn.disabled).toBe(true);

    // Check hostile notes strings are rendered safely as plain text
    // The img tag must NOT exist in the DOM as an HTML image
    const imgElement = document.querySelector("img[src='x']");
    expect(imgElement).toBeNull();
    // The plain text content should be displayed safely
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeDefined();
    expect(screen.getByText('=HYPERLINK("http://malicious.com", "Click Me")')).toBeDefined();

    // Check the skip invalid rows checkbox
    const skipCheckbox = screen.getByLabelText(/Skip 1 invalid rows/i) as HTMLInputElement;
    expect(skipCheckbox.checked).toBe(false);
    fireEvent.click(skipCheckbox);
    expect(skipCheckbox.checked).toBe(true);

    // Now commit button should be enabled!
    expect(commitBtn.disabled).toBe(false);
  });

  it("renders ImportHistory with committed and previewed rows", async () => {
    const mockHistory: ImportSummary[] = [
      {
        ...(importSummaryFixture as unknown as ImportSummary),
        id: "11111111-1111-1111-1111-111111111111",
        filename: "committed-batch.xlsx",
        status: "committed",
        committed_count: 5,
        committed_at: "2026-01-01T10:00:00Z",
      },
      {
        ...(importSummaryFixture as unknown as ImportSummary),
        id: "22222222-2222-2222-2222-222222222222",
        filename: "previewed-batch.xlsx",
        status: "previewed",
      },
    ];
    vi.spyOn(importsApi, "getImportHistory").mockResolvedValue(mockHistory);

    render(
      <QueryClientProvider client={queryClient}>
        <ImportHistory portfolioId="p-123" />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("committed-batch.xlsx")).toBeDefined();
    });

    expect(screen.getAllByText("Committed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: /Undo/i })).toBeDefined();

    expect(screen.getByText("previewed-batch.xlsx")).toBeDefined();
    expect(screen.getByText("Previewed")).toBeDefined();
    expect(screen.getByRole("button", { name: /Discard/i })).toBeDefined();
  });

  it("uploadImportFile helper sends FormData without manual Content-Type header", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        success: true,
        data: {
          import: importSummaryFixture,
          rows: importRowsFixture.items,
        },
      }),
    } as Response);

    const testFile = new File(["dummy content"], "test.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await importsApi.uploadImportFile("p-123", testFile);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const call = fetchSpy.mock.calls[0];
    const url = String(call?.[0] ?? "");
    const options = call?.[1];
    expect(url).toContain("/api/v1/portfolios/p-123/imports");
    expect(options?.method).toBe("POST");
    expect(options?.body instanceof FormData).toBe(true);
    // Crucial check: Content-Type header must NOT be manually set so browser can generate boundary
    const headers = options?.headers as Record<string, string> | undefined;
    expect(headers?.["Content-Type"]).toBeUndefined();
  });
});
