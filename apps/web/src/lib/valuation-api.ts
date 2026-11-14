/**
 * Typed client API functions for Portfolio Valuation, Summary, and Value Series.
 */

import { apiClient } from "./api";
import {
  ValuationResponse,
  ValuationResponseSchema,
  ValuationSummaryResponse,
  ValuationSummaryResponseSchema,
  ValueSeriesResponse,
  ValueSeriesResponseSchema,
  validateContract,
} from "./schemas/contract";

/**
 * Fetch live portfolio valuation, per-position gains, XIRR, and totals.
 */
export async function getPortfolioValuation(
  portfolioId: string,
  includeClosed = false,
): Promise<ValuationResponse> {
  const query = includeClosed ? "?include_closed=true" : "";
  const raw = await apiClient<unknown>(
    `/api/v1/portfolios/${portfolioId}/valuation${query}`,
    { method: "GET" },
  );
  return validateContract(
    ValuationResponseSchema,
    raw,
    "GET /portfolios/{id}/valuation",
  );
}

/**
 * Fetch aggregated multi-portfolio summary, allocation, and top holdings.
 */
export async function getValuationSummary(): Promise<ValuationSummaryResponse> {
  const raw = await apiClient<unknown>("/api/v1/valuation/summary", {
    method: "GET",
  });
  return validateContract(
    ValuationSummaryResponseSchema,
    raw,
    "GET /valuation/summary",
  );
}

/**
 * Fetch historical value-over-time series for a portfolio.
 */
export async function getPortfolioValueSeries(
  portfolioId: string,
  range = "1y",
): Promise<ValueSeriesResponse> {
  const raw = await apiClient<unknown>(
    `/api/v1/portfolios/${portfolioId}/value-series?range=${encodeURIComponent(range)}`,
    { method: "GET" },
  );
  return validateContract(
    ValueSeriesResponseSchema,
    raw,
    "GET /portfolios/{id}/value-series",
  );
}
