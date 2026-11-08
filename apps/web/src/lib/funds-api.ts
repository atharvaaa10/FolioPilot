import { apiClient } from "./api";
import {
  FundDetailResponse,
  FundDetailResponseSchema,
  FundNavHistoryResponse,
  FundNavHistoryResponseSchema,
  FundSearchResponse,
  FundSearchResponseSchema,
  NavStatusResponse,
  NavStatusResponseSchema,
  TrackFundResponse,
  TrackFundResponseSchema,
  validateContract,
} from "./schemas/contract";

export const fundsApi = {
  getNavStatus: async (): Promise<NavStatusResponse> => {
    const raw = await apiClient<NavStatusResponse>("/api/v1/nav/status");
    return validateContract(NavStatusResponseSchema, raw, "fundsApi.getNavStatus");
  },

  searchFunds: async (queryParams: URLSearchParams): Promise<FundSearchResponse> => {
    const query = queryParams.toString();
    const endpoint = query ? `/api/v1/funds/search?${query}` : "/api/v1/funds/search";
    const raw = await apiClient<FundSearchResponse>(endpoint);
    return validateContract(FundSearchResponseSchema, raw, "fundsApi.searchFunds");
  },

  getDetail: async (schemeCode: number | string): Promise<FundDetailResponse> => {
    const raw = await apiClient<FundDetailResponse>(`/api/v1/funds/${schemeCode}`);
    return validateContract(FundDetailResponseSchema, raw, `fundsApi.getDetail(${schemeCode})`);
  },

  getNavHistory: async (schemeCode: number | string): Promise<FundNavHistoryResponse> => {
    const raw = await apiClient<FundNavHistoryResponse>(`/api/v1/funds/${schemeCode}/nav`);
    return validateContract(
      FundNavHistoryResponseSchema,
      raw,
      `fundsApi.getNavHistory(${schemeCode})`,
    );
  },

  trackFund: async (schemeCode: number | string): Promise<TrackFundResponse> => {
    const raw = await apiClient<TrackFundResponse>(`/api/v1/funds/${schemeCode}/track`, {
      method: "POST",
    });
    return validateContract(TrackFundResponseSchema, raw, `fundsApi.trackFund(${schemeCode})`);
  },
};
