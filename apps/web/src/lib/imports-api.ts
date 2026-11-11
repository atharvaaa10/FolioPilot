/**
 * Typed client API functions for Excel Transaction Imports.
 */

import { apiClient, getAccessToken, getBaseApiUrl } from "./api";
import {
  ImportHistoryList,
  ImportHistoryListSchema,
  ImportRowsPageResponse,
  ImportRowsPageResponseSchema,
  ImportSummary,
  ImportSummaryResponseSchema,
  ImportUploadResponse,
  ImportUploadResponseSchema,
  validateContract,
} from "./schemas/contract";

/**
 * Download the official Excel template as a Blob.
 */
export async function downloadTemplateBlob(): Promise<Blob> {
  const baseUrl = getBaseApiUrl();
  const token = getAccessToken();

  const headers: Record<string, string> = {
    Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${baseUrl}/api/v1/imports/template`, {
    method: "GET",
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    throw new Error(`Failed to download template: HTTP ${response.status}`);
  }

  return response.blob();
}

/**
 * Upload an Excel workbook for preview.
 * Uses FormData without manual Content-Type header so browser sets multipart boundary,
 * and participates in single-flight token refresh retry.
 */
export async function uploadImportFile(
  portfolioId: string,
  file: File,
): Promise<ImportUploadResponse> {
  const formData = new FormData();
  formData.append("file", file, file.name);

  const raw = await apiClient<unknown>(`/api/v1/portfolios/${portfolioId}/imports`, {
    method: "POST",
    body: formData,
  });

  return validateContract(ImportUploadResponseSchema, raw, "Upload Import");
}

/**
 * Fetch historical import batches for a portfolio.
 */
export async function getImportHistory(portfolioId: string): Promise<ImportHistoryList> {
  const raw = await apiClient<unknown>(`/api/v1/portfolios/${portfolioId}/imports`, {
    method: "GET",
  });
  return validateContract(ImportHistoryListSchema, raw, "Import History");
}

/**
 * Fetch summary metadata for a single import batch.
 */
export async function getImportSummary(
  portfolioId: string,
  importId: string,
): Promise<ImportSummary> {
  const raw = await apiClient<unknown>(
    `/api/v1/portfolios/${portfolioId}/imports/${importId}`,
    {
      method: "GET",
    },
  );
  return validateContract(ImportSummaryResponseSchema, raw, "Import Summary");
}

/**
 * Fetch paginated preview rows for an active previewed import.
 */
export async function getImportRows(
  portfolioId: string,
  importId: string,
  options: { status?: string; limit?: number; offset?: number } = {},
): Promise<ImportRowsPageResponse> {
  const params = new URLSearchParams();
  if (options.status) {
    params.set("status", options.status);
  }
  if (options.limit !== undefined) {
    params.set("limit", options.limit.toString());
  }
  if (options.offset !== undefined) {
    params.set("offset", options.offset.toString());
  }

  const query = params.toString() ? `?${params.toString()}` : "";
  const raw = await apiClient<unknown>(
    `/api/v1/portfolios/${portfolioId}/imports/${importId}/rows${query}`,
    {
      method: "GET",
    },
  );
  return validateContract(ImportRowsPageResponseSchema, raw, "Import Rows Page");
}

/**
 * Commit a previewed import batch to the portfolio ledger.
 */
export async function commitImport(
  portfolioId: string,
  importId: string,
  payload: { plan_fingerprint: string; skip_invalid: boolean },
): Promise<ImportSummary> {
  const raw = await apiClient<unknown>(
    `/api/v1/portfolios/${portfolioId}/imports/${importId}/commit`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
  return validateContract(ImportSummaryResponseSchema, raw, "Commit Import");
}

/**
 * Undo a committed import batch, removing its ledger transactions.
 */
export async function undoImport(
  portfolioId: string,
  importId: string,
): Promise<ImportSummary> {
  const raw = await apiClient<unknown>(
    `/api/v1/portfolios/${portfolioId}/imports/${importId}/undo`,
    {
      method: "POST",
    },
  );
  return validateContract(ImportSummaryResponseSchema, raw, "Undo Import");
}

/**
 * Discard an uncommitted previewed import.
 */
export async function discardImport(
  portfolioId: string,
  importId: string,
): Promise<{ discarded: boolean }> {
  return apiClient<{ discarded: boolean }>(
    `/api/v1/portfolios/${portfolioId}/imports/${importId}`,
    {
      method: "DELETE",
    },
  );
}
