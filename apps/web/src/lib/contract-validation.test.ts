import { describe, expect, it } from "vitest";
import {
  ApiContractError,
  HoldingSchema,
  PortfolioDetailSchema,
  TransactionItemSchema,
  validateContract,
} from "./schemas/contract";

describe("Runtime API Contract Validation", () => {
  it("passes when valid data matches schema", () => {
    const validPortfolio = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      name: "Retirement",
      description: null,
      created_at: "2026-11-08T10:00:00Z",
      updated_at: "2026-11-08T10:00:00Z",
      targets: [{ asset_class: "equity", target_pct: "100.00" }],
      total_cost_basis: "6400.00",
      open_positions: 1,
      total_transactions: 3,
    };

    const validated = validateContract(
      PortfolioDetailSchema,
      validPortfolio,
      "Portfolio Detail",
    );
    expect(validated.name).toBe("Retirement");
    expect(validated.open_positions).toBe(1);
  });

  it("throws ApiContractError with code CONTRACT_MISMATCH when required field is missing", () => {
    const invalidPortfolio = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      // missing name
      description: null,
      created_at: "2026-11-08T10:00:00Z",
      updated_at: "2026-11-08T10:00:00Z",
      targets: [],
      total_cost_basis: "0.00",
      open_positions: 0,
      total_transactions: 0,
    };

    expect(() =>
      validateContract(PortfolioDetailSchema, invalidPortfolio, "Portfolio Detail"),
    ).toThrow(ApiContractError);

    try {
      validateContract(PortfolioDetailSchema, invalidPortfolio, "Portfolio Detail");
    } catch (err) {
      const contractErr = err as ApiContractError;
      expect(contractErr.code).toBe("CONTRACT_MISMATCH");
      expect(contractErr.path).toBe("name");
      expect(contractErr.message).toContain("invalid field [name]");
    }
  });

  it("throws ApiContractError when transaction has invalid txn_type", () => {
    const invalidTxn = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      portfolio_id: "123e4567-e89b-12d3-a456-426614174001",
      fund_id: "123e4567-e89b-12d3-a456-426614174002",
      txn_type: "INVALID_TYPE",
      txn_date: "2026-11-08",
      units: "10.0000",
      nav: "100.0000",
      amount: "1000.00",
      created_at: "2026-11-08T10:00:00Z",
    };

    try {
      validateContract(TransactionItemSchema, invalidTxn, "Transaction Item");
      expect.unreachable();
    } catch (err) {
      const contractErr = err as ApiContractError;
      expect(contractErr.code).toBe("CONTRACT_MISMATCH");
      expect(contractErr.path).toBe("txn_type");
    }
  });

  it("throws ApiContractError when holding has missing fund metadata", () => {
    const invalidHolding = {
      scheme_code: 122639,
      fund: {
        name: "Parag Parikh Flexi Cap Fund",
        // missing amc, asset_class, etc.
      },
      units: "120.0000",
      avg_cost: "53.3333",
      cost_basis: "6400.00",
      total_bought: "8000.00",
      total_sold: "2100.00",
      first_txn_date: "2025-01-10",
      last_txn_date: "2025-03-10",
      txn_count: 3,
      is_closed: false,
    };

    expect(() =>
      validateContract(HoldingSchema, invalidHolding, "Holding Item"),
    ).toThrow(ApiContractError);
  });
});

