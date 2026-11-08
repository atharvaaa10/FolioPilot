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

export interface PortfolioDetail extends PortfolioSummary {
  total_cost_basis: string;
  open_positions: number;
  total_transactions: number;
}

export interface FundSummary {
  name: string;
  amc: string;
  asset_class: string;
  sub_category: string | null;
  plan_type: string;
  option_type: string;
  latest_nav: string | null;
  latest_nav_date: string | null;
}

export interface Holding {
  scheme_code: number;
  fund: FundSummary;
  units: string;
  avg_cost: string;
  cost_basis: string;
  total_bought: string;
  total_sold: string;
  first_txn_date: string;
  last_txn_date: string;
  txn_count: number;
  is_closed: boolean;
}

export interface HoldingsTotals {
  cost_basis: string;
  open_positions: number;
}

export interface HoldingsResponse {
  items: Holding[];
  totals: HoldingsTotals;
}

export interface TransactionItem {
  id: string;
  portfolio_id: string;
  fund_id: string;
  scheme_code: number | null;
  fund_name: string | null;
  txn_type: "BUY" | "SELL";
  txn_date: string;
  units: string;
  nav: string;
  amount: string;
  notes: string | null;
  created_at: string;
  updated_at?: string | null;
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

export interface UpdateTransactionPayload {
  txn_date?: string;
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

  getHoldings: async (id: string): Promise<HoldingsResponse> => {
    return apiClient<HoldingsResponse>(`/api/v1/portfolios/${id}/holdings`);
  },

  listTransactions: async (id: string): Promise<TransactionItem[]> => {
    return apiClient<TransactionItem[]>(`/api/v1/portfolios/${id}/transactions`);
  },

  getTransaction: async (
    portfolioId: string,
    transactionId: string,
  ): Promise<TransactionItem> => {
    return apiClient<TransactionItem>(
      `/api/v1/portfolios/${portfolioId}/transactions/${transactionId}`,
    );
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

  updateTransaction: async (
    portfolioId: string,
    transactionId: string,
    data: UpdateTransactionPayload,
  ): Promise<TransactionItem> => {
    return apiClient<TransactionItem>(
      `/api/v1/portfolios/${portfolioId}/transactions/${transactionId}`,
      {
        method: "PATCH",
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
