import { apiClient } from "./api";

export interface TargetAllocation {
  asset_class: string;
  target_pct: string;
}

export interface PortfolioSummary {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  targets: TargetAllocation[];
}

export interface Position {
  scheme_code: number;
  fund_name: string;
  asset_class: string;
  units: string;
  avg_nav: string;
  total_invested: string;
  latest_nav: string | null;
  latest_nav_date: string | null;
  current_value: string;
  unrealized_gain: string;
  realized_gain: string;
}

export interface PortfolioDetail extends PortfolioSummary {
  positions: Position[];
  total_invested: string;
  current_value: string;
  unrealized_gain: string;
  realized_gain: string;
}

export interface TransactionItem {
  id: string;
  portfolio_id: string;
  scheme_code: number;
  fund_name: string | null;
  txn_type: "BUY" | "SELL";
  txn_date: string;
  units: string;
  nav: string;
  amount: string;
  notes: string | null;
  created_at: string;
}

export interface CreatePortfolioPayload {
  name: string;
  description?: string;
}

export interface CreateTransactionPayload {
  scheme_code: number;
  txn_type: "BUY" | "SELL";
  txn_date: string;
  units?: string;
  nav?: string;
  amount?: string;
  notes?: string;
}

export const portfoliosApi = {
  list: async (): Promise<PortfolioSummary[]> => {
    return apiClient<PortfolioSummary[]>("/api/v1/portfolios");
  },

  create: async (data: CreatePortfolioPayload): Promise<PortfolioSummary> => {
    return apiClient<PortfolioSummary>("/api/v1/portfolios", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  get: async (id: string): Promise<PortfolioDetail> => {
    return apiClient<PortfolioDetail>(`/api/v1/portfolios/${id}`);
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
    return apiClient<TargetAllocation[]>(`/api/v1/portfolios/${id}/targets`, {
      method: "PUT",
      body: JSON.stringify(targets),
    });
  },

  listTransactions: async (id: string): Promise<TransactionItem[]> => {
    return apiClient<TransactionItem[]>(`/api/v1/portfolios/${id}/transactions`);
  },

  createTransaction: async (
    portfolioId: string,
    data: CreateTransactionPayload,
  ): Promise<TransactionItem> => {
    return apiClient<TransactionItem>(
      `/api/v1/portfolios/${portfolioId}/transactions`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    );
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

