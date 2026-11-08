import { describe, expect, it } from "vitest";
import { z } from "zod";
import {
  FundDetailResponseSchema,
  FundNavHistoryResponseSchema,
  FundSearchResponseSchema,
  HoldingsResponseSchema,
  InsufficientUnitsErrorSchema,
  LedgerInconsistentErrorSchema,
  NavStatusResponseSchema,
  PortfolioDetailSchema,
  TargetAllocationSchema,
  TrackFundResponseSchema,
  TransactionListResponseSchema,
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
});

