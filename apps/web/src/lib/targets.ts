import Decimal from "decimal.js";

export const MAX_TARGET_ROWS = 5;

export const VALID_ASSET_CLASSES = ["equity", "debt", "hybrid", "gold", "other"] as const;
export type AssetClass = (typeof VALID_ASSET_CLASSES)[number];

export interface TargetItem {
  asset_class: string;
  target_pct: string;
}

export interface TargetValidationError {
  index: number;
  field: "asset_class" | "target_pct";
  message: string;
}

export interface TargetsSummary {
  totalPct: string;
  remainingPct: string;
  isExactHundred: boolean;
  isValid: boolean;
  canSave: boolean;
  errors: TargetValidationError[];
  generalError: string | null;
}

/**
 * Evaluates target allocations using exact decimal arithmetic.
 * Ensures 33.33 + 33.33 + 33.34 equals exactly 100.00.
 */
export function evaluateTargets(targets: TargetItem[] = []): TargetsSummary {
  const safeTargets = Array.isArray(targets) ? targets : [];
  const errors: TargetValidationError[] = [];
  let generalError: string | null = null;

  if (safeTargets.length > MAX_TARGET_ROWS) {
    generalError = `Cannot configure more than ${MAX_TARGET_ROWS} target allocations`;
  }

  const seenClasses = new Set<string>();
  let runningTotal = new Decimal("0.00");

  safeTargets.forEach((target, index) => {
    const rawClass = target.asset_class?.trim().toLowerCase();
    const rawPct = target.target_pct?.trim();

    // Validate asset class
    if (!rawClass) {
      errors.push({
        index,
        field: "asset_class",
        message: "Asset class is required",
      });
    } else if (!VALID_ASSET_CLASSES.includes(rawClass as AssetClass)) {
      errors.push({
        index,
        field: "asset_class",
        message: `Invalid asset class. Must be one of: ${VALID_ASSET_CLASSES.join(", ")}`,
      });
    } else if (seenClasses.has(rawClass)) {
      errors.push({
        index,
        field: "asset_class",
        message: `Duplicate asset class '${rawClass}'`,
      });
    } else {
      seenClasses.add(rawClass);
    }

    // Validate target percentage
    if (!rawPct) {
      errors.push({
        index,
        field: "target_pct",
        message: "Percentage is required",
      });
    } else {
      try {
        const pct = new Decimal(rawPct);
        if (!pct.isFinite() || pct.isNaN()) {
          errors.push({
            index,
            field: "target_pct",
            message: "Must be a valid number",
          });
        } else if (pct.lte(0) || pct.gt(100)) {
          errors.push({
            index,
            field: "target_pct",
            message: "Must be greater than 0 and at most 100",
          });
        } else if (pct.decimalPlaces() > 2) {
          errors.push({
            index,
            field: "target_pct",
            message: "Maximum 2 decimal places allowed",
          });
        } else {
          runningTotal = runningTotal.plus(pct);
        }
      } catch {
        errors.push({
          index,
          field: "target_pct",
          message: "Must be a valid number",
        });
      }
    }
  });

  const totalStr = runningTotal.toFixed(2);
  const remaining = new Decimal("100.00").minus(runningTotal);
  const remainingStr = remaining.toFixed(2);
  const isExactHundred = runningTotal.equals(new Decimal("100.00"));

  // Empty targets is valid (portfolio has no target allocations set)
  // If targets are provided, must have no errors, row count <= 5, and total === 100.00
  let isValid = false;
  let canSave = false;

  if (safeTargets.length === 0) {
    isValid = true;
    canSave = true;
  } else {
    isValid = errors.length === 0 && generalError === null && isExactHundred;
    canSave = isValid;
    if (errors.length === 0 && generalError === null && !isExactHundred) {
      generalError = `Allocations sum to ${totalStr}%. They must sum to exactly 100.00% (${remaining.gt(0) ? `${remainingStr}% remaining` : `${runningTotal.minus(100).toFixed(2)}% over`}).`;
    }
  }

  return {
    totalPct: totalStr,
    remainingPct: remainingStr,
    isExactHundred,
    isValid,
    canSave,
    errors,
    generalError,
  };
}

