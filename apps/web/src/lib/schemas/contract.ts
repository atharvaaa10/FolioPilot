import { z } from "zod";

/**
 * Custom Error thrown when an API response violates the runtime contract schema.
 */
export class ApiContractError extends Error {
  public readonly code = "CONTRACT_MISMATCH";
  public readonly path: string;
  public readonly issues: z.ZodIssue[];

  constructor(message: string, path: string, issues: z.ZodIssue[]) {
    super(message);
    this.name = "ApiContractError";
    this.path = path;
    this.issues = issues;
    Object.setPrototypeOf(this, ApiContractError.prototype);
  }
}

/**
 * Validates data against a Zod schema or throws a typed ApiContractError.
 */
export function validateContract<T>(
  schema: z.ZodType<T, z.ZodTypeDef, any>,
  data: unknown,
  contextName = "API Response"
): T {
  const result = schema.safeParse(data);
  if (!result.success) {
    const errorPath =
      result.error.issues.map((i) => i.path.join(".")).filter(Boolean).join(", ") || "root";
    throw new ApiContractError(
      `Contract mismatch in ${contextName}: invalid field [${errorPath}] - ${result.error.issues[0]?.message}`,
      errorPath,
      result.error.issues,
    );
  }
  return result.data;
}

// -------------------------------------------------------------
// Target Allocations
// -------------------------------------------------------------
export const TargetAllocationSchema = z.object({
  asset_class: z.string(),
  target_pct: z.string(),
});
export type TargetAllocation = z.infer<typeof TargetAllocationSchema>;

// -------------------------------------------------------------
// Portfolios
// -------------------------------------------------------------
export const PortfolioSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  targets: z.array(TargetAllocationSchema).default([]),
});
export type PortfolioSummary = z.infer<typeof PortfolioSummarySchema>;

export const PortfolioDetailSchema = PortfolioSummarySchema.extend({
  total_cost_basis: z.string(),
  open_positions: z.number(),
  total_transactions: z.number(),
});
export type PortfolioDetail = z.infer<typeof PortfolioDetailSchema>;

// -------------------------------------------------------------
// Holdings
// -------------------------------------------------------------
export const FundSummarySchema = z.object({
  name: z.string(),
  amc: z.string(),
  asset_class: z.string(),
  sub_category: z.string().nullable(),
  plan_type: z.string(),
  option_type: z.string(),
  latest_nav: z.string().nullable().optional(),
  latest_nav_date: z.string().nullable().optional(),
});
export type FundSummary = z.infer<typeof FundSummarySchema>;

export const HoldingSchema = z.object({
  scheme_code: z.number(),
  fund: FundSummarySchema,
  units: z.string(),
  avg_cost: z.string(),
  cost_basis: z.string(),
  total_bought: z.string(),
  total_sold: z.string(),
  first_txn_date: z.string(),
  last_txn_date: z.string(),
  txn_count: z.number(),
  is_closed: z.boolean(),
});
export type Holding = z.infer<typeof HoldingSchema>;

export const HoldingsTotalsSchema = z.object({
  cost_basis: z.string(),
  open_positions: z.number(),
});
export type HoldingsTotals = z.infer<typeof HoldingsTotalsSchema>;

export const HoldingsResponseSchema = z.object({
  items: z.array(HoldingSchema),
  totals: HoldingsTotalsSchema,
});
export type HoldingsResponse = z.infer<typeof HoldingsResponseSchema>;

// -------------------------------------------------------------
// Transactions
// -------------------------------------------------------------
export const TransactionTypeEnum = z.enum(["buy", "sell", "dividend_reinvest"]);
export type TransactionType = z.infer<typeof TransactionTypeEnum>;

export const TransactionItemSchema = z.object({
  id: z.string().uuid(),
  portfolio_id: z.string().uuid(),
  fund_id: z.string().uuid(),
  scheme_code: z.number().nullable().optional(),
  fund_name: z.string().nullable().optional(),
  txn_type: TransactionTypeEnum,
  txn_date: z.string(),
  units: z.string(),
  nav: z.string(),
  amount: z.string(),
  notes: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string().nullable().optional(),
});
export type TransactionItem = z.infer<typeof TransactionItemSchema>;

export const TransactionListResponseSchema = z.object({
  items: z.array(TransactionItemSchema),
  has_more: z.boolean().default(false),
});
export type TransactionListResponse = z.infer<typeof TransactionListResponseSchema>;

// -------------------------------------------------------------
// Funds & NAV
// -------------------------------------------------------------
export const FundSearchItemSchema = z.object({
  id: z.string().uuid(),
  scheme_code: z.number(),
  name: z.string(),
  amc: z.string(),
  category_raw: z.string(),
  asset_class: z.string(),
  sub_category: z.string().nullable(),
  plan_type: z.string(),
  option_type: z.string(),
  latest_nav: z.union([z.string(), z.number()]).nullable(),
  latest_nav_date: z.string().nullable(),
  is_active: z.boolean(),
  is_tracked: z.boolean(),
});
export type FundSearchItem = z.infer<typeof FundSearchItemSchema>;

export const FundSearchResponseSchema = z.object({
  items: z.array(FundSearchItemSchema),
  has_more: z.boolean(),
});
export type FundSearchResponse = z.infer<typeof FundSearchResponseSchema>;

export const FundDetailResponseSchema = z.object({
  id: z.string().uuid(),
  scheme_code: z.number(),
  isin_growth: z.string().nullable(),
  isin_reinvest: z.string().nullable(),
  name: z.string(),
  amc: z.string(),
  scheme_type_raw: z.string().nullable(),
  category_raw: z.string(),
  asset_class: z.string(),
  sub_category: z.string().nullable(),
  classification_source: z.string(),
  plan_type: z.string(),
  option_type: z.string(),
  latest_nav: z.union([z.string(), z.number()]).nullable(),
  latest_nav_date: z.string().nullable(),
  is_active: z.boolean(),
  is_tracked: z.boolean(),
});
export type FundDetailResponse = z.infer<typeof FundDetailResponseSchema>;

export const NavPointSchema = z.object({
  date: z.string(),
  nav: z.union([z.string(), z.number()]),
});
export type NavPoint = z.infer<typeof NavPointSchema>;

export const FundNavHistoryResponseSchema = z.object({
  scheme_code: z.number(),
  name: z.string(),
  history_available: z.boolean(),
  points: z.array(NavPointSchema),
});
export type FundNavHistoryResponse = z.infer<typeof FundNavHistoryResponseSchema>;

export const TrackFundResponseSchema = z.object({
  scheme_code: z.number(),
  status: z.enum(["queued", "already_tracked"]),
});
export type TrackFundResponse = z.infer<typeof TrackFundResponseSchema>;

export const NavStatusResponseSchema = z.object({
  last_run_time: z.string().nullable(),
  last_run_status: z.string().nullable(),
  last_success_time: z.string().nullable(),
  schemes_parsed: z.number(),
  funds_created: z.number(),
  funds_updated: z.number(),
  nav_rows_written: z.number(),
  is_stale: z.boolean(),
});
export type NavStatusResponse = z.infer<typeof NavStatusResponseSchema>;

// -------------------------------------------------------------
// Spec Error Details Schemas
// -------------------------------------------------------------
export const InsufficientUnitsErrorSchema = z.object({
  code: z.literal("INSUFFICIENT_UNITS"),
  message: z.string(),
  details: z.object({
    available_units: z.string(),
    date: z.string(),
  }),
});

export const LedgerInconsistentErrorSchema = z.object({
  code: z.literal("LEDGER_INCONSISTENT"),
  message: z.string(),
  details: z.object({
    fund: z.string().optional(),
    fund_id: z.string().optional(),
    date: z.string(),
  }),
});

