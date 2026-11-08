import Decimal from "decimal.js";

export interface TransactionHintInputs {
  units?: string;
  nav?: string;
  amount?: string;
}

export interface TransactionHintResult {
  derivedField: "units" | "nav" | "amount" | null;
  derivedValue: string | null;
  hintMessage: string | null;
  isValid: boolean;
  error: string | null;
}

export const AMOUNT_TOLERANCE_ABSOLUTE = new Decimal("1.00");
export const AMOUNT_TOLERANCE_RELATIVE = new Decimal("0.002");

function parseDecimal(val?: string): Decimal | null {
  if (!val) return null;
  const trimmed = val.trim();
  if (trimmed === "") return null;
  try {
    const d = new Decimal(trimmed);
    if (!d.isFinite() || d.isNaN()) return null;
    return d;
  } catch {
    return null;
  }
}

/**
 * Derives the third transaction value given any two of {units, nav, amount},
 * or validates consistency within tolerance when all three are provided.
 */
export function deriveTransactionValues(inputs: TransactionHintInputs): TransactionHintResult {
  const { units: rawUnits, nav: rawNav, amount: rawAmount } = inputs;

  const hasUnits = rawUnits !== undefined && rawUnits.trim() !== "";
  const hasNav = rawNav !== undefined && rawNav.trim() !== "";
  const hasAmount = rawAmount !== undefined && rawAmount.trim() !== "";

  const units = parseDecimal(rawUnits);
  const nav = parseDecimal(rawNav);
  const amount = parseDecimal(rawAmount);

  // Validate non-empty but unparseable inputs
  if (hasUnits && (units === null || units.lte(0))) {
    return {
      derivedField: null,
      derivedValue: null,
      hintMessage: null,
      isValid: false,
      error: "Units must be a positive number",
    };
  }
  if (hasNav && (nav === null || nav.lte(0))) {
    return {
      derivedField: null,
      derivedValue: null,
      hintMessage: null,
      isValid: false,
      error: "NAV must be a positive number",
    };
  }
  if (hasAmount && (amount === null || amount.lte(0))) {
    return {
      derivedField: null,
      derivedValue: null,
      hintMessage: null,
      isValid: false,
      error: "Amount must be a positive number",
    };
  }

  // Validate decimal scale limits
  if (units !== null && units.decimalPlaces() > 4) {
    return {
      derivedField: null,
      derivedValue: null,
      hintMessage: null,
      isValid: false,
      error: "Units cannot exceed 4 decimal places",
    };
  }
  if (nav !== null && nav.decimalPlaces() > 8) {
    return {
      derivedField: null,
      derivedValue: null,
      hintMessage: null,
      isValid: false,
      error: "NAV cannot exceed 8 decimal places",
    };
  }
  if (amount !== null && amount.decimalPlaces() > 2) {
    return {
      derivedField: null,
      derivedValue: null,
      hintMessage: null,
      isValid: false,
      error: "Amount cannot exceed 2 decimal places",
    };
  }

  // Case 1: Units and NAV provided -> derive Amount
  if (units !== null && nav !== null && amount === null) {
    const derived = units.times(nav).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
    const formatted = derived.toFixed(2);
    return {
      derivedField: "amount",
      derivedValue: formatted,
      hintMessage: `Auto-calculated Amount: ₹${formatted} (${units.toString()} × ₹${nav.toString()})`,
      isValid: true,
      error: null,
    };
  }

  // Case 2: Amount and NAV provided -> derive Units
  if (amount !== null && nav !== null && units === null) {
    const derived = amount.dividedBy(nav).toDecimalPlaces(4, Decimal.ROUND_HALF_UP);
    const formatted = derived.toFixed(4);
    return {
      derivedField: "units",
      derivedValue: formatted,
      hintMessage: `Auto-calculated Units: ${formatted} (₹${amount.toFixed(2)} ÷ ₹${nav.toString()})`,
      isValid: true,
      error: null,
    };
  }

  // Case 3: Amount and Units provided -> derive NAV
  if (amount !== null && units !== null && nav === null) {
    const derived = amount.dividedBy(units).toDecimalPlaces(4, Decimal.ROUND_HALF_UP);
    const formatted = derived.toFixed(4);
    return {
      derivedField: "nav",
      derivedValue: formatted,
      hintMessage: `Auto-calculated NAV: ₹${formatted} (₹${amount.toFixed(2)} ÷ ${units.toString()})`,
      isValid: true,
      error: null,
    };
  }

  // Case 4: All three provided -> validate consistency
  if (units !== null && nav !== null && amount !== null) {
    const product = units.times(nav);
    const diff = product.minus(amount).abs();
    const tolerance = Decimal.max(AMOUNT_TOLERANCE_ABSOLUTE, AMOUNT_TOLERANCE_RELATIVE.times(amount));

    if (diff.lte(tolerance)) {
      return {
        derivedField: null,
        derivedValue: null,
        hintMessage: "Values match within tolerance.",
        isValid: true,
        error: null,
      };
    } else {
      return {
        derivedField: null,
        derivedValue: null,
        hintMessage: null,
        isValid: false,
        error: `Amount ₹${amount.toFixed(2)} differs from units × NAV = ₹${product.toFixed(2)} by ₹${diff.toFixed(2)} (tolerance ₹${tolerance.toFixed(2)})`,
      };
    }
  }

  // Case 5: Fewer than 2 values provided
  return {
    derivedField: null,
    derivedValue: null,
    hintMessage: "Fill any two fields to calculate the third automatically.",
    isValid: true,
    error: null,
  };
}

