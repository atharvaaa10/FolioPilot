"use client";

import * as React from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, RefreshCw } from "lucide-react";

import { AuthGate } from "@/components/auth/auth-gate";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AllocationDonut } from "@/components/valuation/allocation-donut";
import {
  ValuationCards,
  formatXirrPercent,
} from "@/components/valuation/valuation-cards";
import { ValueSeriesChart } from "@/components/valuation/value-series-chart";
import { formatDate, formatInr, formatSignedGain, formatUnits } from "@/lib/format";
import type { ValuationSummaryResponse } from "@/lib/schemas/contract";
import { getValuationSummary } from "@/lib/valuation-api";

function DashboardContent() {
  const [data, setData] = React.useState<ValuationSummaryResponse | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);

  const fetchSummary = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getValuationSummary();
      setData(res);
    } catch (err: any) {
      setError(err?.message || "Failed to load investment dashboard. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  if (loading) {
    return (
      <div className="container mx-auto max-w-7xl space-y-8 p-4 py-8 sm:px-8">
        <div className="flex flex-col gap-2">
          <div className="h-8 w-64 animate-pulse rounded bg-muted" />
          <div className="h-4 w-48 animate-pulse rounded bg-muted" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <div className="h-4 w-24 animate-pulse rounded bg-muted" />
              </CardHeader>
              <CardContent>
                <div className="h-7 w-32 animate-pulse rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto max-w-7xl space-y-8 p-4 py-8 sm:px-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error loading dashboard</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={fetchSummary} className="ml-4">
              <RefreshCw className="mr-2 h-4 w-4" />
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const hasPortfolios = data && data.counts.portfolios > 0;
  const hasOpenPositions = data && data.counts.open_positions > 0;
  const hasTransactions = data && data.totals.cost_basis !== "0.00";

  // Empty state for users without portfolios or transactions
  if (!hasPortfolios || (!hasOpenPositions && !hasTransactions)) {
    return (
      <div className="container mx-auto max-w-7xl space-y-8 p-4 py-8 sm:px-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Investor Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time portfolio valuation, gains, and XIRR performance.
          </p>
        </div>

        <Card className="border-dashed p-8 text-center">
          <CardContent className="space-y-4 pt-6">
            <h3 className="text-lg font-semibold">No investment activity yet</h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              Create a portfolio and record or import transactions to unlock real-time valuation,
              capital gains, asset allocation, and XIRR performance analysis.
            </p>
            <Button asChild className="mt-4">
              <Link href="/portfolios">
                Go to Portfolios
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const hasFallback = data.totals.fallback_positions > 0;
  const hasStale = data.totals.stale_positions > 0;

  return (
    <div className="container mx-auto max-w-7xl space-y-8 p-4 py-8 sm:px-8">
      {/* Header with As-of date */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Investor Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Valuation as of{" "}
            <span className="font-medium text-foreground">
              {formatDate(data.as_of)}
            </span>
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchSummary}>
          <RefreshCw className="mr-2 h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {/* Warning banner for fallback cost or stale positions */}
      {(hasFallback || hasStale) && (
        <Alert className="border-amber-500/50 bg-amber-50/50 text-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
          <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertTitle className="font-semibold">Valuation Notice</AlertTitle>
          <AlertDescription className="text-xs space-y-1">
            {hasFallback && (
              <p>
                {data.totals.fallback_positions} position(s) lack official AMFI NAV data and are
                valued using weighted average cost basis (excluded from portfolio XIRR).
              </p>
            )}
            {hasStale && (
              <p>
                {data.totals.stale_positions} position(s) have NAV updates older than 7 calendar days.
              </p>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* 1. Summary Cards */}
      <ValuationCards totals={data.totals} />

      {/* 2. Charts Row: Allocation Donut & Value-over-time */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AllocationDonut items={data.allocation.by_asset_class} />
        {data.portfolios.length > 0 && (
          <ValueSeriesChart
            portfolioId={data.portfolios[0]?.id}
            title={`Value Trend (${data.portfolios[0]?.name || "Portfolio"})`}
          />
        )}
      </div>

      {/* 3. Portfolios Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Portfolios Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Portfolio</TableHead>
                <TableHead className="text-right">Cost Basis</TableHead>
                <TableHead className="text-right">Current Value</TableHead>
                <TableHead className="text-right">Unrealized Gain</TableHead>
                <TableHead className="text-right">Realized Gain</TableHead>
                <TableHead className="text-right">XIRR</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.portfolios.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">
                    <Link
                      href={`/portfolios/${p.id}`}
                      className="text-primary hover:underline font-semibold"
                    >
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatInr(p.cost_basis)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm font-semibold">
                    {formatInr(p.current_value)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatSignedGain(p.unrealized_gain, p.unrealized_gain_pct)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatInr(p.realized_gain)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm font-medium">
                    {formatXirrPercent(p.xirr.rate)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 4. Top Holdings Table */}
      {data.top_holdings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">Top Holdings</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scheme / Fund</TableHead>
                  <TableHead>Asset Class</TableHead>
                  <TableHead className="text-right">Units</TableHead>
                  <TableHead className="text-right">Current Value</TableHead>
                  <TableHead className="text-right">Unrealized Gain</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.top_holdings.map((h) => (
                  <TableRow key={h.scheme_code}>
                    <TableCell>
                      <div className="font-medium">{h.fund.name}</div>
                      <div className="text-xs text-muted-foreground">{h.fund.amc}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize text-xs">
                        {h.fund.asset_class}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatUnits(h.units)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm font-semibold">
                      {formatInr(h.current_value)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatInr(h.unrealized_gain)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function DashboardPage(): React.JSX.Element {
  return (
    <AuthGate>
      <DashboardContent />
    </AuthGate>
  );
}
