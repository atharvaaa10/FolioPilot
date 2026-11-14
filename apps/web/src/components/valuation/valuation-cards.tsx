"use client";

import * as React from "react";
import { Info, Minus, TrendingDown, TrendingUp } from "lucide-react";
import Decimal from "decimal.js";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatInr, formatSignedGain } from "@/lib/format";
import type { ValuationTotals, XirrResult } from "@/lib/schemas/contract";

export function getXirrMessage(xirr: XirrResult): string {
  if (xirr.rate !== null) {
    let msg = "Annualised internal rate of return calculated from cash flows and terminal value.";
    if (xirr.short_period) {
      msg += " Annualised over less than a year.";
    }
    if (xirr.ambiguous) {
      msg += " Multiple solutions exist; rate with smallest magnitude shown.";
    }
    if (xirr.excluded_funds > 0) {
      msg += ` Excludes ${xirr.excluded_funds} fund(s) without live NAV.`;
    }
    return msg;
  }

  switch (xirr.reason) {
    case "NO_TRANSACTIONS":
      return "No transactions in scope.";
    case "NO_NAV_DATA":
      return "No live NAV data available for open positions.";
    case "INSUFFICIENT_FLOWS":
      return "At least two distinct cash flow dates with inflows and outflows required.";
    case "PERIOD_TOO_SHORT":
      return "Investment period is under 30 days. XIRR is not meaningful.";
    case "NO_SOLUTION":
      return "No valid mathematical solution found for cash flows.";
    default:
      return "XIRR not available.";
  }
}

export function formatXirrPercent(rate: string | null | undefined): string {
  if (!rate) {
    return "—";
  }
  try {
    const d = new Decimal(rate).times(100).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
    const sign = d.isPositive() && !d.isZero() ? "+" : "";
    return `${sign}${d.toFixed(2)}%`;
  } catch {
    return "—";
  }
}

interface ValuationCardsProps {
  totals: ValuationTotals;
}

export function ValuationCards({ totals }: ValuationCardsProps): React.JSX.Element {
  const dGain = new Decimal(totals.unrealized_gain || "0");
  const isGainPos = dGain.isPositive() && !dGain.isZero();
  const isGainNeg = dGain.isNegative();

  const gainIcon = isGainPos ? (
    <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
  ) : isGainNeg ? (
    <TrendingDown className="h-4 w-4 text-rose-600 dark:text-rose-400" />
  ) : (
    <Minus className="h-4 w-4 text-muted-foreground" />
  );

  const gainColor = isGainPos
    ? "text-emerald-600 dark:text-emerald-400"
    : isGainNeg
    ? "text-rose-600 dark:text-rose-400"
    : "text-foreground";

  return (
    <TooltipProvider>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {/* 1. Current Value */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Current Value</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight">
              {formatInr(totals.current_value)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {totals.open_positions} open {totals.open_positions === 1 ? "position" : "positions"}
            </p>
          </CardContent>
        </Card>

        {/* 2. Cost Basis */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Cost Basis</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight">
              {formatInr(totals.cost_basis)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Weighted average cost</p>
          </CardContent>
        </Card>

        {/* 3. Unrealized Gain */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Unrealized Gain</CardTitle>
            {gainIcon}
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold tracking-tight ${gainColor}`}>
              {formatSignedGain(totals.unrealized_gain, totals.unrealized_gain_pct)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">On current open holdings</p>
          </CardContent>
        </Card>

        {/* 4. Realized Gain */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Realized Gain</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight">
              {formatInr(totals.realized_gain)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Total booked profits</p>
          </CardContent>
        </Card>

        {/* 5. XIRR */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div className="flex items-center gap-1.5">
              <CardTitle className="text-sm font-medium">XIRR</CardTitle>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button type="button" aria-label="XIRR explanation" className="text-muted-foreground hover:text-foreground">
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  {getXirrMessage(totals.xirr)}
                </TooltipContent>
              </Tooltip>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight">
              {formatXirrPercent(totals.xirr.rate)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {totals.xirr.rate
                ? totals.xirr.short_period
                  ? "Annualised (< 1 year)"
                  : "Annualised return"
                : totals.xirr.reason || "No return data"}
            </p>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}
