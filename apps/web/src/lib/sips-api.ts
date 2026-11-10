import { apiClient } from "./api";
import {
  SipDetail,
  SipDetailSchema,
  SipInstallment,
  SipInstallmentSchema,
  SipInstallmentsListResponse,
  SipInstallmentsListResponseSchema,
  SipListResponse,
  SipListResponseSchema,
  SipPreviewResponse,
  SipPreviewResponseSchema,
  validateContract,
} from "./schemas/contract";

export interface CreateSipPayload {
  scheme_code?: number;
  fund_id?: string;
  amount: string;
  day_of_month: number;
  start_date: string;
  end_date?: string | null;
  step_up_percent?: string;
  notes?: string | null;
}

export interface PatchSipPayload {
  notes?: string | null;
  end_date?: string | null;
}

export interface ListInstallmentsParams {
  status?: string;
  limit?: number;
  offset?: number;
}

export const sipsApi = {
  list: async (portfolioId: string, status?: string): Promise<SipListResponse> => {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    const raw = await apiClient<SipListResponse>(`/api/v1/portfolios/${portfolioId}/sips${query}`);
    return validateContract(SipListResponseSchema, raw, "sipsApi.list");
  },

  get: async (portfolioId: string, sipId: string): Promise<SipDetail> => {
    const raw = await apiClient<SipDetail>(`/api/v1/portfolios/${portfolioId}/sips/${sipId}`);
    return validateContract(SipDetailSchema, raw, `sipsApi.get(${sipId})`);
  },

  preview: async (
    portfolioId: string,
    payload: CreateSipPayload,
    count: number = 12
  ): Promise<SipPreviewResponse> => {
    const raw = await apiClient<SipPreviewResponse>(
      `/api/v1/portfolios/${portfolioId}/sips/preview?count=${count}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
    return validateContract(SipPreviewResponseSchema, raw, "sipsApi.preview");
  },

  create: async (portfolioId: string, payload: CreateSipPayload): Promise<SipDetail> => {
    const raw = await apiClient<SipDetail>(`/api/v1/portfolios/${portfolioId}/sips`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return validateContract(SipDetailSchema, raw, "sipsApi.create");
  },

  patch: async (
    portfolioId: string,
    sipId: string,
    payload: PatchSipPayload
  ): Promise<SipDetail> => {
    const raw = await apiClient<SipDetail>(
      `/api/v1/portfolios/${portfolioId}/sips/${sipId}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      }
    );
    return validateContract(SipDetailSchema, raw, `sipsApi.patch(${sipId})`);
  },

  pause: async (portfolioId: string, sipId: string, fromDate?: string): Promise<SipDetail> => {
    const raw = await apiClient<SipDetail>(
      `/api/v1/portfolios/${portfolioId}/sips/${sipId}/pause`,
      {
        method: "POST",
        body: JSON.stringify(fromDate ? { from_date: fromDate } : {}),
      }
    );
    return validateContract(SipDetailSchema, raw, `sipsApi.pause(${sipId})`);
  },

  resume: async (portfolioId: string, sipId: string, onDate?: string): Promise<SipDetail> => {
    const raw = await apiClient<SipDetail>(
      `/api/v1/portfolios/${portfolioId}/sips/${sipId}/resume`,
      {
        method: "POST",
        body: JSON.stringify(onDate ? { on_date: onDate } : {}),
      }
    );
    return validateContract(SipDetailSchema, raw, `sipsApi.resume(${sipId})`);
  },

  end: async (portfolioId: string, sipId: string, endDate?: string): Promise<SipDetail> => {
    const raw = await apiClient<SipDetail>(
      `/api/v1/portfolios/${portfolioId}/sips/${sipId}/end`,
      {
        method: "POST",
        body: JSON.stringify(endDate ? { end_date: endDate } : {}),
      }
    );
    return validateContract(SipDetailSchema, raw, `sipsApi.end(${sipId})`);
  },

  delete: async (portfolioId: string, sipId: string): Promise<void> => {
    await apiClient<void>(`/api/v1/portfolios/${portfolioId}/sips/${sipId}`, {
      method: "DELETE",
    });
  },

  listInstallments: async (
    portfolioId: string,
    sipId: string,
    params?: ListInstallmentsParams
  ): Promise<SipInstallmentsListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString() ? `?${searchParams.toString()}` : "";

    const raw = await apiClient<SipInstallmentsListResponse>(
      `/api/v1/portfolios/${portfolioId}/sips/${sipId}/installments${qs}`
    );
    return validateContract(SipInstallmentsListResponseSchema, raw, "sipsApi.listInstallments");
  },

  skipInstallment: async (
    portfolioId: string,
    sipId: string,
    installmentId: string
  ): Promise<SipInstallment> => {
    const raw = await apiClient<SipInstallment>(
      `/api/v1/portfolios/${portfolioId}/sips/${sipId}/installments/${installmentId}/skip`,
      {
        method: "POST",
      }
    );
    return validateContract(SipInstallmentSchema, raw, "sipsApi.skipInstallment");
  },
};
