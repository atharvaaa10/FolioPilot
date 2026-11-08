import { apiClient } from "./api";
import {
  FundSummary,
  Holding,
  HoldingsResponse,
  HoldingsResponseSchema,
  HoldingsTotals,
  PortfolioDetail,
  PortfolioDetailSchema,
  PortfolioSummary,
  PortfolioSummarySchema,
  TargetAllocation,
  TargetAllocationSchema,
  TransactionItem,
  TransactionItemSchema,
  TransactionListResponse,
  TransactionListResponseSchema,
  TransactionType,
  validateContract,
} from "./schemas/contract";
import { z } from "zod";

export type {
  FundSummary,
  Holding,
  HoldingsResponse,
  HoldingsTotals,
  PortfolioDetail,
  PortfolioSummary,
  TargetAllocation,
  TransactionItem,
  TransactionListResponse,
  TransactionType,
};

export interface CreatePortfolioPayload {
  name: string;
  description?: string;
}

export interface CreateTransactionPayload {
  scheme_code: number;
  txn_type: TransactionType;
  txn_date: string;
  units?: string;
  nav?: string;
  amount?: string;
  notes?: string;
}

export interface UpdateTransactionPayload {
  txn_date?: string;
  units?: string;
  nav?: string;
  amount?: string;
  notes?: string;
}

export const portfoliosApi = {
  list: async (): Promise<PortfolioSummary[]> => {
    const raw = await apiClient<PortfolioSummary[]>("/api/v1/portfolios");
    return validateContract(z.array(PortfolioSummarySchema), raw, "portfoliosApi.list");
  },

  create: async (data: CreatePortfolioPayload): Promise<PortfolioSummary> => {
    const raw = await apiClient<PortfolioSummary>("/api/v1/portfolios", {
      method: "POST",
      body: JSON.stringify(data),
    });
    return validateContract(PortfolioSummarySchema, raw, "portfoliosApi.create");
  },

  get: async (id: string): Promise<PortfolioDetail> => {
    const raw = await apiClient<PortfolioDetail>(`/api/v1/portfolios/${id}`);
    return validateContract(PortfolioDetailSchema, raw, `portfoliosApi.get(${id})`);
  },

  delete: async (id: string): Promise<void> => {
    return apiClient<void>(`/api/v1/portfolios/${id}`, {
      method: "DELETE",
    });
  },

  updateTargets: async (
    id: string,
    targets: TargetAllocation[],
  ): Promise<TargetAllocation[]> => {
    const raw = await apiClient<TargetAllocation[]>(`/api/v1/portfolios/${id}/targets`, {
      method: "PUT",
      body: JSON.stringify(targets),
    });
    return validateContract(z.array(TargetAllocationSchema), raw, "portfoliosApi.updateTargets");
  },

  getHoldings: async (id: string): Promise<HoldingsResponse> => {
    const raw = await apiClient<HoldingsResponse>(`/api/v1/portfolios/${id}/holdings`);
    return validateContract(HoldingsResponseSchema, raw, `portfoliosApi.getHoldings(${id})`);
  },

  listTransactions: async (id: string): Promise<TransactionListResponse> => {
    const raw = await apiClient<TransactionListResponse>(`/api/v1/portfolios/${id}/transactions`);
    return validateContract(
      TransactionListResponseSchema,
      raw,
      `portfoliosApi.listTransactions(${id})`,
    );
  },

  getTransaction: async (
    portfolioId: string,
    transactionId: string,
  ): Promise<TransactionItem> => {
    const raw = await apiClient<TransactionItem>(
      `/api/v1/portfolios/${portfolioId}/transactions/${transactionId}`,
    );
    return validateContract(
      TransactionItemSchema,
      raw,
      `portfoliosApi.getTransaction(${transactionId})`,
    );
  },

  createTransaction: async (
    portfolioId: string,
    data: CreateTransactionPayload,
  ): Promise<TransactionItem> => {
    const raw = await apiClient<TransactionItem>(
      `/api/v1/portfolios/${portfolioId}/transactions`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    );
    return validateContract(TransactionItemSchema, raw, "portfoliosApi.createTransaction");
  },

  updateTransaction: async (
    portfolioId: string,
    transactionId: string,
    data: UpdateTransactionPayload,
  ): Promise<TransactionItem> => {
    const raw = await apiClient<TransactionItem>(
      `/api/v1/portfolios/${portfolioId}/transactions/${transactionId}`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    );
    return validateContract(TransactionItemSchema, raw, "portfoliosApi.updateTransaction");
  },

  deleteTransaction: async (
    portfolioId: string,
    transactionId: string,
  ): Promise<void> => {
    return apiClient<void>(
      `/api/v1/portfolios/${portfolioId}/transactions/${transactionId}`,
      {
        method: "DELETE",
      },
    );
  },
};
