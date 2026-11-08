import { describe, expect, it } from "vitest";
import { deriveTransactionValues } from "./transaction-hint";

describe("deriveTransactionValues", () => {
  it("derives amount when units and nav are provided", () => {
    const result = deriveTransactionValues({
      units: "100.5",
      nav: "25.25",
    });
    expect(result.isValid).toBe(true);
    expect(result.derivedField).toBe("amount");
    expect(result.derivedValue).toBe("2537.63"); // 100.5 * 25.25 = 2537.625 -> 2537.63
    expect(result.error).toBeNull();
  });

  it("derives units when amount and nav are provided", () => {
    const result = deriveTransactionValues({
      amount: "5000",
      nav: "33.3333",
    });
    expect(result.isValid).toBe(true);
    expect(result.derivedField).toBe("units");
    expect(result.derivedValue).toBe("150.0002");
    expect(result.error).toBeNull();
  });

  it("derives nav when amount and units are provided", () => {
    const result = deriveTransactionValues({
      amount: "10000",
      units: "200",
    });
    expect(result.isValid).toBe(true);
    expect(result.derivedField).toBe("nav");
    expect(result.derivedValue).toBe("50.0000");
    expect(result.error).toBeNull();
  });

  it("accepts all three when within tolerance", () => {
    // 100 * 10 = 1000, provided amount = 1000.50 (within ₹1.00 absolute tolerance)
    const result = deriveTransactionValues({
      units: "100",
      nav: "10",
      amount: "1000.50",
    });
    expect(result.isValid).toBe(true);
    expect(result.derivedField).toBeNull();
    expect(result.derivedValue).toBeNull();
    expect(result.error).toBeNull();
  });

  it("rejects all three when mismatch exceeds tolerance", () => {
    // 100 * 10 = 1000, provided amount = 1010 (exceeds ₹2.02 relative tolerance)
    const result = deriveTransactionValues({
      units: "100",
      nav: "10",
      amount: "1010",
    });
    expect(result.isValid).toBe(false);
    expect(result.error).toContain("differs from units × NAV");
  });

  it("returns helpful prompt when fewer than two fields are provided", () => {
    const result = deriveTransactionValues({
      units: "100",
    });
    expect(result.isValid).toBe(true);
    expect(result.derivedField).toBeNull();
    expect(result.hintMessage).toContain("Fill any two fields");
  });

  it("flags scale limit errors", () => {
    const unitsResult = deriveTransactionValues({ units: "1.12345", nav: "10" });
    expect(unitsResult.isValid).toBe(false);
    expect(unitsResult.error).toContain("Units cannot exceed 4 decimal places");

    const amountResult = deriveTransactionValues({ amount: "100.123", nav: "10" });
    expect(amountResult.isValid).toBe(false);
    expect(amountResult.error).toContain("Amount cannot exceed 2 decimal places");
  });

  it("flags negative or zero numbers", () => {
    const zeroResult = deriveTransactionValues({ units: "0", nav: "10" });
    expect(zeroResult.isValid).toBe(false);
    expect(zeroResult.error).toContain("Units must be a positive number");

    const negResult = deriveTransactionValues({ amount: "-500", nav: "10" });
    expect(negResult.isValid).toBe(false);
    expect(negResult.error).toContain("Amount must be a positive number");
  });
});

