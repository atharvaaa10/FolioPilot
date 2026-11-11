import { describe, expect, it } from "vitest";
import { z } from "zod";
import {
  FundDetailResponseSchema,
  FundInactiveErrorSchema,
  FundNavHistoryResponseSchema,
  FundSearchResponseSchema,
  HoldingsResponseSchema,
  ImportAlreadyCommittedErrorSchema,
  ImportFileInvalidErrorSchema,
  ImportFileTooLargeErrorSchema,
  ImportHasErrorsErrorSchema,
  ImportHistoryListSchema,
  ImportNothingToImportErrorSchema,
  ImportRowsPageResponseSchema,
  ImportStaleErrorSchema,
  ImportSummaryResponseSchema,
  ImportTemplateMismatchErrorSchema,
  InstallmentNotSkippableErrorSchema,
  InsufficientUnitsErrorSchema,
  LedgerInconsistentErrorSchema,
  NavStatusResponseSchema,
  PortfolioDetailSchema,
  SipAlreadyEndedErrorSchema,
  SipAlreadyPausedErrorSchema,
  SipDetailSchema,
  SipInstallmentsListResponseSchema,
  SipInvalidScheduleErrorSchema,
  SipListResponseSchema,
  SipNotPausedErrorSchema,
  SipPreviewResponseSchema,
  TargetAllocationSchema,
  TrackFundResponseSchema,
  TransactionListResponseSchema,
  TransactionManagedBySipErrorSchema,
  validateContract,
} from "@/lib/schemas/contract";

import portfolioDetailFixture from "./fixtures/contract/portfolio-detail.json";
import holdingsFixture from "./fixtures/contract/holdings.json";
import transactionsFixture from "./fixtures/contract/transactions.json";
import targetsFixture from "./fixtures/contract/targets.json";
import insufficientUnitsFixture from "./fixtures/contract/error-insufficient-units.json";
import ledgerInconsistentFixture from "./fixtures/contract/error-ledger-inconsistent.json";
import fundsSearchFixture from "./fixtures/contract/funds-search.json";
import fundDetailFixture from "./fixtures/contract/fund-detail.json";
import navHistoryFixture from "./fixtures/contract/nav-history.json";
import navStatusFixture from "./fixtures/contract/nav-status.json";
import trackFundFixture from "./fixtures/contract/track-fund.json";
import sipDetailFixture from "./fixtures/contract/sip-detail.json";
import sipsListFixture from "./fixtures/contract/sips-list.json";
import sipInstallmentsFixture from "./fixtures/contract/sip-installments.json";
import sipPreviewFixture from "./fixtures/contract/sip-preview.json";
import errorSipInvalidScheduleFixture from "./fixtures/contract/error-sip-invalid-schedule.json";
import errorSipAlreadyPausedFixture from "./fixtures/contract/error-sip-already-paused.json";
import errorSipNotPausedFixture from "./fixtures/contract/error-sip-not-paused.json";
import errorSipAlreadyEndedFixture from "./fixtures/contract/error-sip-already-ended.json";
import errorTransactionManagedBySipFixture from "./fixtures/contract/error-transaction-managed-by-sip.json";
import errorInstallmentNotSkippableFixture from "./fixtures/contract/error-installment-not-skippable.json";
import errorFundInactiveFixture from "./fixtures/contract/error-fund-inactive.json";
import importSummaryFixture from "./fixtures/contract/import-summary.json";
import importRowsFixture from "./fixtures/contract/import-rows.json";
import importHistoryFixture from "./fixtures/contract/import-history.json";
import errorImportAlreadyCommittedFixture from "./fixtures/contract/error-import-already-committed.json";
import errorImportFileInvalidFixture from "./fixtures/contract/error-import-file-invalid.json";
import errorImportFileTooLargeFixture from "./fixtures/contract/error-import-file-too-large.json";
import errorImportHasErrorsFixture from "./fixtures/contract/error-import-has-errors.json";
import errorImportNothingToImportFixture from "./fixtures/contract/error-import-nothing-to-import.json";
import errorImportStaleFixture from "./fixtures/contract/error-import-stale.json";
import errorImportTemplateMismatchFixture from "./fixtures/contract/error-import-template-mismatch.json";

describe("Committed Contract Fixtures Validation", () => {
  it("validates portfolio-detail.json against PortfolioDetailSchema", () => {
    const data = validateContract(
      PortfolioDetailSchema,
      portfolioDetailFixture,
      "portfolio-detail.json",
    );
    expect(data.name).toBe("Retirement");
    expect(data.open_positions).toBe(1);
    expect(data.total_cost_basis).toBe("6400.00");
  });

  it("validates holdings.json against HoldingsResponseSchema", () => {
    const data = validateContract(
      HoldingsResponseSchema,
      holdingsFixture,
      "holdings.json",
    );
    expect(data.items.length).toBe(1);
    expect(data.items[0]?.fund.sub_category).toBe("flexi-cap");
    expect(data.totals.cost_basis).toBe("6400.00");
  });

  it("validates transactions.json against TransactionListResponseSchema", () => {
    const data = validateContract(
      TransactionListResponseSchema,
      transactionsFixture,
      "transactions.json",
    );
    expect(data.items.length).toBe(3);
    expect(data.items[0]?.txn_type).toBe("buy");
    expect(data.items[2]?.txn_type).toBe("sell");
  });

  it("validates targets.json against TargetAllocationSchema array", () => {
    const data = validateContract(
      z.array(TargetAllocationSchema),
      targetsFixture,
      "targets.json",
    );
    expect(data.length).toBe(3);
  });

  it("validates error fixtures against spec error schemas", () => {
    const errUnits = validateContract(
      InsufficientUnitsErrorSchema,
      insufficientUnitsFixture,
      "error-insufficient-units.json",
    );
    expect(errUnits.code).toBe("INSUFFICIENT_UNITS");
    expect(errUnits.details.available_units).toBe("120.0000");

    const errLedger = validateContract(
      LedgerInconsistentErrorSchema,
      ledgerInconsistentFixture,
      "error-ledger-inconsistent.json",
    );
    expect(errLedger.code).toBe("LEDGER_INCONSISTENT");
    expect(errLedger.details.date).toBe("2025-04-10");
  });

  it("validates funds fixtures against fund schemas", () => {
    const searchData = validateContract(
      FundSearchResponseSchema,
      fundsSearchFixture,
      "funds-search.json",
    );
    expect(searchData.items.length).toBe(1);

    const detailData = validateContract(
      FundDetailResponseSchema,
      fundDetailFixture,
      "fund-detail.json",
    );
    expect(detailData.scheme_code).toBe(122639);

    const navHist = validateContract(
      FundNavHistoryResponseSchema,
      navHistoryFixture,
      "nav-history.json",
    );
    expect(navHist.points.length).toBe(3);

    const navStatus = validateContract(
      NavStatusResponseSchema,
      navStatusFixture,
      "nav-status.json",
    );
    expect(navStatus.is_stale).toBe(false);

    const track = validateContract(
      TrackFundResponseSchema,
      trackFundFixture,
      "track-fund.json",
    );
    expect(track.status).toBe("already_tracked");
  });

  it("validates SIP fixtures against SIP schemas", () => {
    const sipDetail = validateContract(
      SipDetailSchema,
      sipDetailFixture,
      "sip-detail.json",
    );
    expect(sipDetail.amount).toBe("5000.00");
    expect(sipDetail.day_of_month).toBe(10);
    expect(sipDetail.fund.scheme_code).toBe(122639);
    expect(sipDetail.status).toBe("active");

    const sipsList = validateContract(
      SipListResponseSchema,
      sipsListFixture,
      "sips-list.json",
    );
    expect(sipsList.items.length).toBe(1);
    expect(sipsList.total).toBe(1);

    const installments = validateContract(
      SipInstallmentsListResponseSchema,
      sipInstallmentsFixture,
      "sip-installments.json",
    );
    expect(installments.items.length).toBe(2);
    expect(installments.items[0]?.status).toBe("executed");
    expect(installments.items[0]?.transaction?.units).toBe("90.2527");
    expect(installments.items[1]?.status).toBe("pending");
    expect(installments.items[1]?.transaction).toBeNull();

    const preview = validateContract(
      SipPreviewResponseSchema,
      sipPreviewFixture,
      "sip-preview.json",
    );
    expect(preview.items.length).toBe(6);
    expect(preview.count).toBe(6);
  });

  it("validates SIP error fixtures against spec error schemas", () => {
    const errSched = validateContract(
      SipInvalidScheduleErrorSchema,
      errorSipInvalidScheduleFixture,
      "error-sip-invalid-schedule.json",
    );
    expect(errSched.code).toBe("SIP_INVALID_SCHEDULE");

    const errPaused = validateContract(
      SipAlreadyPausedErrorSchema,
      errorSipAlreadyPausedFixture,
      "error-sip-already-paused.json",
    );
    expect(errPaused.code).toBe("SIP_ALREADY_PAUSED");

    const errNotPaused = validateContract(
      SipNotPausedErrorSchema,
      errorSipNotPausedFixture,
      "error-sip-not-paused.json",
    );
    expect(errNotPaused.code).toBe("SIP_NOT_PAUSED");

    const errEnded = validateContract(
      SipAlreadyEndedErrorSchema,
      errorSipAlreadyEndedFixture,
      "error-sip-already-ended.json",
    );
    expect(errEnded.code).toBe("SIP_ALREADY_ENDED");

    const errManaged = validateContract(
      TransactionManagedBySipErrorSchema,
      errorTransactionManagedBySipFixture,
      "error-transaction-managed-by-sip.json",
    );
    expect(errManaged.code).toBe("TRANSACTION_MANAGED_BY_SIP");

    const errNotSkip = validateContract(
      InstallmentNotSkippableErrorSchema,
      errorInstallmentNotSkippableFixture,
      "error-installment-not-skippable.json",
    );
    expect(errNotSkip.code).toBe("INSTALLMENT_NOT_SKIPPABLE");

    const errInactive = validateContract(
      FundInactiveErrorSchema,
      errorFundInactiveFixture,
      "error-fund-inactive.json",
    );
    expect(errInactive.code).toBe("FUND_INACTIVE");
  });

  it("validates Phase 4 import contract fixtures and error schemas", () => {
    const summary = validateContract(
      ImportSummaryResponseSchema,
      importSummaryFixture,
      "import-summary.json",
    );
    expect(summary.status).toBe("previewed");
    expect(summary.rows_total).toBe(3);
    expect(summary.will_import).toBe(3);

    const rows = validateContract(
      ImportRowsPageResponseSchema,
      importRowsFixture,
      "import-rows.json",
    );
    expect(rows.items.length).toBe(1);
    expect(rows.items[0]?.status).toBe("ok");

    const history = validateContract(
      ImportHistoryListSchema,
      importHistoryFixture,
      "import-history.json",
    );
    expect(history.length).toBe(1);
    expect(history[0]?.status).toBe("previewed");

    const errCommitted = validateContract(
      ImportAlreadyCommittedErrorSchema,
      errorImportAlreadyCommittedFixture,
      "error-import-already-committed.json",
    );
    expect(errCommitted.code).toBe("IMPORT_ALREADY_COMMITTED");

    const errInvalid = validateContract(
      ImportFileInvalidErrorSchema,
      errorImportFileInvalidFixture,
      "error-import-file-invalid.json",
    );
    expect(errInvalid.code).toBe("IMPORT_FILE_INVALID");

    const errTooLarge = validateContract(
      ImportFileTooLargeErrorSchema,
      errorImportFileTooLargeFixture,
      "error-import-file-too-large.json",
    );
    expect(errTooLarge.code).toBe("IMPORT_FILE_TOO_LARGE");

    const errHasErrors = validateContract(
      ImportHasErrorsErrorSchema,
      errorImportHasErrorsFixture,
      "error-import-has-errors.json",
    );
    expect(errHasErrors.code).toBe("IMPORT_HAS_ERRORS");

    const errNothing = validateContract(
      ImportNothingToImportErrorSchema,
      errorImportNothingToImportFixture,
      "error-import-nothing-to-import.json",
    );
    expect(errNothing.code).toBe("IMPORT_NOTHING_TO_IMPORT");

    const errStale = validateContract(
      ImportStaleErrorSchema,
      errorImportStaleFixture,
      "error-import-stale.json",
    );
    expect(errStale.code).toBe("IMPORT_STALE");

    const errMismatch = validateContract(
      ImportTemplateMismatchErrorSchema,
      errorImportTemplateMismatchFixture,
      "error-import-template-mismatch.json",
    );
    expect(errMismatch.code).toBe("IMPORT_TEMPLATE_MISMATCH");
  });
});

