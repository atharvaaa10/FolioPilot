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
  sip_installment_id: z.string().uuid().nullable().optional(),
  import_id: z.string().uuid().nullable().optional(),
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

// -------------------------------------------------------------
// SIPs (Systematic Investment Plans)
// -------------------------------------------------------------
export const SipStatusEnum = z.enum(["scheduled", "active", "paused", "ended"]);
export type SipStatus = z.infer<typeof SipStatusEnum>;

export const SipFundSchema = z.object({
  scheme_code: z.number(),
  name: z.string(),
  amc: z.string(),
  plan_type: z.string(),
  option_type: z.string(),
  asset_class: z.string(),
  sub_category: z.string().nullable().optional(),
});
export type SipFund = z.infer<typeof SipFundSchema>;

export const SipPauseSchema = z.object({
  id: z.string().uuid(),
  paused_from: z.string(),
  resumed_on: z.string().nullable(),
});
export type SipPause = z.infer<typeof SipPauseSchema>;

export const SipStatsSchema = z.object({
  installments_total: z.number(),
  executed: z.number(),
  pending: z.number(),
  skipped: z.number(),
  total_invested: z.string(),
  units_acquired: z.string(),
});
export type SipStats = z.infer<typeof SipStatsSchema>;

export const SipDetailSchema = z.object({
  id: z.string().uuid(),
  portfolio_id: z.string().uuid(),
  fund: SipFundSchema,
  amount: z.string(),
  day_of_month: z.number(),
  start_date: z.string(),
  end_date: z.string().nullable(),
  step_up_percent: z.string(),
  notes: z.string().nullable().optional(),
  status: SipStatusEnum,
  next_due_date: z.string().nullable().optional(),
  next_installment_amount: z.string().nullable().optional(),
  pauses: z.array(SipPauseSchema),
  stats: SipStatsSchema,
  created_at: z.string(),
});
export type SipDetail = z.infer<typeof SipDetailSchema>;

export const SipListResponseSchema = z.object({
  items: z.array(SipDetailSchema),
  total: z.number(),
});
export type SipListResponse = z.infer<typeof SipListResponseSchema>;

export const SipInstallmentTransactionSchema = z.object({
  id: z.string().uuid(),
  txn_date: z.string(),
  units: z.string(),
  nav: z.string(),
  amount: z.string(),
});
export type SipInstallmentTransaction = z.infer<typeof SipInstallmentTransactionSchema>;

export const SipInstallmentStatusEnum = z.enum(["pending", "executed", "skipped"]);
export type SipInstallmentStatus = z.infer<typeof SipInstallmentStatusEnum>;

export const SipInstallmentSchema = z.object({
  id: z.string().uuid(),
  sip_id: z.string().uuid(),
  due_date: z.string(),
  planned_amount: z.string(),
  status: SipInstallmentStatusEnum,
  nav_date: z.string().nullable().optional(),
  transaction: SipInstallmentTransactionSchema.nullable().optional(),
});
export type SipInstallment = z.infer<typeof SipInstallmentSchema>;

export const SipInstallmentsListResponseSchema = z.object({
  items: z.array(SipInstallmentSchema),
  total: z.number(),
  has_more: z.boolean(),
  limit: z.number(),
  offset: z.number(),
});
export type SipInstallmentsListResponse = z.infer<typeof SipInstallmentsListResponseSchema>;

export const SipPreviewItemSchema = z.object({
  due_date: z.string(),
  planned_amount: z.string(),
});
export type SipPreviewItem = z.infer<typeof SipPreviewItemSchema>;

export const SipPreviewResponseSchema = z.object({
  items: z.array(SipPreviewItemSchema),
  count: z.number(),
});
export type SipPreviewResponse = z.infer<typeof SipPreviewResponseSchema>;

// -------------------------------------------------------------
// SIP Specific Error Details Schemas
// -------------------------------------------------------------
export const SipInvalidScheduleErrorSchema = z.object({
  code: z.literal("SIP_INVALID_SCHEDULE"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

export const SipAlreadyPausedErrorSchema = z.object({
  code: z.literal("SIP_ALREADY_PAUSED"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

export const SipNotPausedErrorSchema = z.object({
  code: z.literal("SIP_NOT_PAUSED"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

export const SipAlreadyEndedErrorSchema = z.object({
  code: z.literal("SIP_ALREADY_ENDED"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

export const TransactionManagedBySipErrorSchema = z.object({
  code: z.literal("TRANSACTION_MANAGED_BY_SIP"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

export const InstallmentNotSkippableErrorSchema = z.object({
  code: z.literal("INSTALLMENT_NOT_SKIPPABLE"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

export const FundInactiveErrorSchema = z.object({
  code: z.literal("FUND_INACTIVE"),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});

// -------------------------------------------------------------
// Excel Transaction Imports (Phase 4)
// -------------------------------------------------------------
export const ImportFundSummarySchema = z.object({
  scheme_code: z.number(),
  name: z.string(),
  amc: z.string().nullable().optional(),
  plan_type: z.string().nullable().optional(),
  option_type: z.string().nullable().optional(),
  is_active: z.boolean().default(true),
});
export type ImportFundSummary = z.infer<typeof ImportFundSummarySchema>;

export const RowMessageSchema = z.object({
  level: z.enum(["error", "warning", "info"]),
  code: z.string(),
  field: z.string().nullable().optional(),
  message: z.string(),
  details: z.unknown().optional(),
});
export type RowMessage = z.infer<typeof RowMessageSchema>;

export const ImportRowResponseSchema = z.object({
  row_number: z.number(),
  status: z.enum(["ok", "warning", "duplicate", "error"]),
  fund: ImportFundSummarySchema.nullable().optional(),
  fund_name_in_file: z.string().nullable().optional(),
  txn_type: z.string().nullable().optional(),
  txn_date: z.string().nullable().optional(),
  units: z.string().nullable().optional(),
  nav: z.string().nullable().optional(),
  amount: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  raw: z.record(z.string()).default({}),
  messages: z.array(RowMessageSchema).default([]),
});
export type ImportRow = z.infer<typeof ImportRowResponseSchema>;

export const ImportDateRangeSchema = z.object({
  from: z.string().nullable().optional(),
  to: z.string().nullable().optional(),
});

export const ImportTotalsSchema = z.object({
  buy_amount: z.string().default("0.00"),
  sell_amount: z.string().default("0.00"),
});

export const ImportSummaryResponseSchema = z.object({
  id: z.string().uuid(),
  portfolio_id: z.string().uuid(),
  filename: z.string(),
  file_sha256: z.string(),
  status: z.enum(["previewed", "committed", "undone"]),
  rows_total: z.number(),
  rows_ok: z.number(),
  rows_warning: z.number(),
  rows_duplicate: z.number(),
  rows_error: z.number(),
  will_import: z.number(),
  plan_fingerprint: z.string(),
  extra_columns: z.array(z.string()).nullable().optional(),
  funds_count: z.number().default(0),
  date_range: ImportDateRangeSchema.nullable().optional(),
  totals: ImportTotalsSchema.default({ buy_amount: "0.00", sell_amount: "0.00" }),
  blocking_errors: z.array(z.string()).default([]),
  previewed_at: z.string(),
  expires_at: z.string(),
  committed_count: z.number().nullable().optional(),
  committed_at: z.string().nullable().optional(),
  undone_count: z.number().nullable().optional(),
  undone_at: z.string().nullable().optional(),
});
export type ImportSummary = z.infer<typeof ImportSummaryResponseSchema>;

export const ImportUploadResponseSchema = z.object({
  import: ImportSummaryResponseSchema,
  rows: z.array(ImportRowResponseSchema),
});
export type ImportUploadResponse = z.infer<typeof ImportUploadResponseSchema>;

export const ImportRowsPageResponseSchema = z.object({
  items: z.array(ImportRowResponseSchema),
  has_more: z.boolean().default(false),
});
export type ImportRowsPageResponse = z.infer<typeof ImportRowsPageResponseSchema>;

export const ImportHistoryListSchema = z.array(ImportSummaryResponseSchema);
export type ImportHistoryList = z.infer<typeof ImportHistoryListSchema>;

// Phase 4 Import Errors
export const ImportFileInvalidErrorSchema = z.object({
  code: z.literal("IMPORT_FILE_INVALID"),
  message: z.string(),
  details: z.unknown().optional(),
});

export const ImportFileTooLargeErrorSchema = z.object({
  code: z.literal("IMPORT_FILE_TOO_LARGE"),
  message: z.string(),
  details: z.unknown().optional(),
});

export const ImportTemplateMismatchErrorSchema = z.object({
  code: z.literal("IMPORT_TEMPLATE_MISMATCH"),
  message: z.string(),
  details: z.unknown().optional(),
});

export const ImportHasErrorsErrorSchema = z.object({
  code: z.literal("IMPORT_HAS_ERRORS"),
  message: z.string(),
  details: z.unknown().optional(),
});

export const ImportStaleErrorSchema = z.object({
  code: z.literal("IMPORT_STALE"),
  message: z.string(),
  details: z.unknown().optional(),
});

export const ImportNothingToImportErrorSchema = z.object({
  code: z.literal("IMPORT_NOTHING_TO_IMPORT"),
  message: z.string(),
  details: z.unknown().optional(),
});

export const ImportAlreadyCommittedErrorSchema = z.object({
  code: z.literal("IMPORT_ALREADY_COMMITTED"),
  message: z.string(),
  details: z.unknown().optional(),
});


