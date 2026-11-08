"use client";

import * as React from "react";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  HelpCircle,
  Loader2,
  Plus,
  PlusCircle,
  Search,
  Trash2,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import {
  portfoliosApi,
  type CreateTransactionPayload,
  type PortfolioDetail,
  type TargetAllocation,
  type TransactionItem,
} from "@/lib/portfolios-api";
import {
  formatCurrency,
  formatDateString,
  formatGainLoss,
  formatNav,
  formatUnits,
  getAssetClassBadge,
  getTodayIsoDate,
} from "@/lib/formatters";
import { evaluateTargets, VALID_ASSET_CLASSES } from "@/lib/targets";
import { deriveTransactionValues } from "@/lib/transaction-hint";
import { useDebounce } from "@/hooks/use-debounce";
import { apiClient } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { FundSearchItem, FundSearchResponse } from "@/types/funds";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function PortfolioDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  // Portfolio Detail Query
  const {
    data: portfolio,
    isLoading: isPortfolioLoading,
    error: portfolioError,
  } = useQuery<PortfolioDetail>({
    queryKey: ["portfolio", id],
    queryFn: () => portfoliosApi.get(id),
  });

  // Transactions Query
  const {
    data: transactions = [],
    isLoading: isTxnsLoading,
  } = useQuery<TransactionItem[]>({
    queryKey: ["transactions", id],
    queryFn: () => portfoliosApi.listTransactions(id),
  });

  // Target Allocations State
  const [targetRows, setTargetRows] = useState<TargetAllocation[]>([]);
  const [hasTargetsChanged, setHasTargetsChanged] = useState(false);
  const [targetsMessage, setTargetsMessage] = useState<string | null>(null);

  // Sync targets state from server query
  useEffect(() => {
    if (portfolio?.targets) {
      setTargetRows(portfolio.targets);
      setHasTargetsChanged(false);
    }
  }, [portfolio?.targets]);

  const targetsEvaluation = evaluateTargets(targetRows);

  const updateTargetsMutation = useMutation({
    mutationFn: (targets: TargetAllocation[]) =>
      portfoliosApi.updateTargets(id, targets),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      setHasTargetsChanged(false);
      setTargetsMessage("Target allocations updated successfully.");
      setTimeout(() => setTargetsMessage(null), 4000);
    },
    onError: (err: { message?: string }) => {
      setTargetsMessage(err.message || "Failed to update target allocations.");
    },
  });

  // Add Transaction Modal State
  const [isAddTxnOpen, setIsAddTxnOpen] = useState(false);
  const [fundSearch, setFundSearch] = useState("");
  const debouncedFundSearch = useDebounce(fundSearch, 300);
  const [selectedFund, setSelectedFund] = useState<FundSearchItem | null>(null);
  const [manualSchemeCode, setManualSchemeCode] = useState("");

  const [txnType, setTxnType] = useState<"BUY" | "SELL">("BUY");
  const [txnDate, setTxnDate] = useState(() => getTodayIsoDate());
  const [txnUnits, setTxnUnits] = useState("");
  const [txnNav, setTxnNav] = useState("");
  const [txnAmount, setTxnAmount] = useState("");
  const [txnNotes, setTxnNotes] = useState("");
  const [txnError, setTxnError] = useState<string | null>(null);

  // Fund search query inside dialog
  const { data: fundSearchResults, isFetching: isSearchingFunds } =
    useQuery<FundSearchResponse>({
      queryKey: ["fund-picker", debouncedFundSearch],
      queryFn: () =>
        apiClient<FundSearchResponse>(
          `/api/v1/funds/search?q=${encodeURIComponent(debouncedFundSearch)}&limit=8`,
        ),
      enabled: isAddTxnOpen && debouncedFundSearch.trim().length >= 2,
    });

  // Calculate live derivation hints
  const hintResult = deriveTransactionValues({
    units: txnUnits,
    nav: txnNav,
    amount: txnAmount,
  });

  // Auto-fill NAV when fund is selected if user hasn't typed one
  useEffect(() => {
    if (selectedFund && selectedFund.latest_nav !== null && selectedFund.latest_nav !== undefined && !txnNav) {
      setTxnNav(String(selectedFund.latest_nav));
    }
  }, [selectedFund, txnNav]);

  const addTxnMutation = useMutation({
    mutationFn: (payload: CreateTransactionPayload) =>
      portfoliosApi.createTransaction(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      queryClient.invalidateQueries({ queryKey: ["transactions", id] });
      setIsAddTxnOpen(false);
      resetTxnForm();
    },
    onError: (err: { message?: string }) => {
      setTxnError(err.message || "Failed to record transaction.");
    },
  });

  const deleteTxnMutation = useMutation({
    mutationFn: (txnId: string) => portfoliosApi.deleteTransaction(id, txnId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      queryClient.invalidateQueries({ queryKey: ["transactions", id] });
    },
    onError: (err: { message?: string }) => {
      alert(err.message || "Failed to delete transaction.");
    },
  });

  const resetTxnForm = () => {
    setFundSearch("");
    setSelectedFund(null);
    setManualSchemeCode("");
    setTxnType("BUY");
    setTxnUnits("");
    setTxnNav("");
    setTxnAmount("");
    setTxnNotes("");
    setTxnError(null);
  };

  const handleTxnSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setTxnError(null);

    const schemeCode = selectedFund
      ? selectedFund.scheme_code
      : parseInt(manualSchemeCode.trim(), 10);

    if (!schemeCode || Number.isNaN(schemeCode)) {
      setTxnError("Please select a mutual fund or enter a valid AMFI scheme code.");
      return;
    }

    if (!txnDate) {
      setTxnError("Transaction date is required.");
      return;
    }

    // Must provide at least two of units, nav, amount
    const filledCount = [txnUnits, txnNav, txnAmount].filter(
      (v) => v.trim() !== "",
    ).length;

    if (filledCount < 2) {
      setTxnError("Please fill at least two of Units, NAV, and Amount.");
      return;
    }

    if (!hintResult.isValid) {
      setTxnError(hintResult.error || "Invalid transaction values.");
      return;
    }

    // Auto-fill derived value if applicable
    let finalUnits = txnUnits.trim() || undefined;
    let finalNav = txnNav.trim() || undefined;
    let finalAmount = txnAmount.trim() || undefined;

    if (hintResult.derivedField === "amount" && hintResult.derivedValue) {
      finalAmount = hintResult.derivedValue;
    } else if (hintResult.derivedField === "units" && hintResult.derivedValue) {
      finalUnits = hintResult.derivedValue;
    } else if (hintResult.derivedField === "nav" && hintResult.derivedValue) {
      finalNav = hintResult.derivedValue;
    }

    addTxnMutation.mutate({
      scheme_code: schemeCode,
      txn_type: txnType,
      txn_date: txnDate,
      units: finalUnits,
      nav: finalNav,
      amount: finalAmount,
      notes: txnNotes.trim() || undefined,
    });
  };

  if (isPortfolioLoading) {
    return (
      <div className="container mx-auto flex h-96 items-center justify-center px-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (portfolioError || !portfolio) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-16">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Portfolio Not Found</AlertTitle>
          <AlertDescription>
            {(portfolioError as { message?: string })?.message ||
              "The requested portfolio could not be found or you do not have permission to view it."}
          </AlertDescription>
        </Alert>
        <div className="mt-6 text-center">
          <Link href="/portfolios">
            <Button variant="outline" className="inline-flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              <span>Back to Portfolios</span>
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  const unrealizedGain = formatGainLoss(portfolio.unrealized_gain);
  const realizedGain = formatGainLoss(portfolio.realized_gain);

  return (
    <div className="container mx-auto space-y-8 px-4 py-8 sm:px-8">
      {/* Top Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link
            href="/portfolios"
            className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Portfolios</span>
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">{portfolio.name}</h1>
          {portfolio.description && (
            <p className="mt-1 text-sm text-muted-foreground">
              {portfolio.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={() => setIsAddTxnOpen(true)}
            className="inline-flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            <span>Add Transaction</span>
          </Button>
        </div>
      </div>

      {/* Summary Metrics Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Total Invested
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {formatCurrency(portfolio.total_invested)}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Net capital cost basis
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Current Value
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {formatCurrency(portfolio.current_value)}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            At latest available NAV
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Unrealized Gain / Loss
            </CardDescription>
            <CardTitle
              className={`text-2xl font-bold flex items-center gap-1 ${
                unrealizedGain.isPositive
                  ? "text-emerald-600 dark:text-emerald-400"
                  : unrealizedGain.isNegative
                    ? "text-rose-600 dark:text-rose-400"
                    : ""
              }`}
            >
              {unrealizedGain.isPositive && <TrendingUp className="h-5 w-5" />}
              {unrealizedGain.isNegative && <TrendingDown className="h-5 w-5" />}
              <span>{unrealizedGain.formatted}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Current Value − Invested
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Realized Gain / Loss
            </CardDescription>
            <CardTitle
              className={`text-2xl font-bold flex items-center gap-1 ${
                realizedGain.isPositive
                  ? "text-emerald-600 dark:text-emerald-400"
                  : realizedGain.isNegative
                    ? "text-rose-600 dark:text-rose-400"
                    : ""
              }`}
            >
              {realizedGain.isPositive && <TrendingUp className="h-5 w-5" />}
              {realizedGain.isNegative && <TrendingDown className="h-5 w-5" />}
              <span>{realizedGain.formatted}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            From settled redemptions
          </CardContent>
        </Card>
      </div>

      {/* Target Asset Allocation Editor */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="text-lg font-semibold">
                Target Asset Allocation
              </CardTitle>
              <CardDescription>
                Define target weightings across asset classes. Exact total must equal 100.00%.
              </CardDescription>
            </div>

            <div className="flex items-center gap-3">
              <Badge
                variant="outline"
                className={`font-mono text-sm px-3 py-1 ${
                  targetsEvaluation.isExactHundred
                    ? "border-emerald-500 text-emerald-600 bg-emerald-500/10"
                    : "border-amber-500 text-amber-600 bg-amber-500/10"
                }`}
              >
                Total: {targetsEvaluation.totalPct}%
              </Badge>

              <Button
                size="sm"
                disabled={
                  !hasTargetsChanged ||
                  !targetsEvaluation.canSave ||
                  updateTargetsMutation.isPending
                }
                onClick={() => updateTargetsMutation.mutate(targetRows)}
              >
                {updateTargetsMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  "Save Targets"
                )}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {targetsMessage && (
            <Alert
              variant={
                targetsMessage.includes("success") ? "default" : "destructive"
              }
            >
              <AlertDescription>{targetsMessage}</AlertDescription>
            </Alert>
          )}

          {targetsEvaluation.generalError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {targetsEvaluation.generalError}
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-3">
            {targetRows.map((target, index) => {
              const classErr = targetsEvaluation.errors.find(
                (e) => e.index === index && e.field === "asset_class",
              );
              const pctErr = targetsEvaluation.errors.find(
                (e) => e.index === index && e.field === "target_pct",
              );

              return (
                <div
                  key={index}
                  className="flex flex-col gap-2 sm:flex-row sm:items-center"
                >
                  <div className="w-full sm:w-48">
                    <Select
                      value={target.asset_class}
                      onValueChange={(val) => {
                        const updated = [...targetRows];
                        const current = updated[index];
                        if (current) {
                          updated[index] = { ...current, asset_class: val };
                          setTargetRows(updated);
                          setHasTargetsChanged(true);
                        }
                      }}
                    >
                      <SelectTrigger className={classErr ? "border-destructive" : ""}>
                        <SelectValue placeholder="Select class" />
                      </SelectTrigger>
                      <SelectContent>
                        {VALID_ASSET_CLASSES.map((cls) => (
                          <SelectItem key={cls} value={cls}>
                            <span className="capitalize">{cls}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {classErr && (
                      <p className="mt-1 text-xs text-destructive">
                        {classErr.message}
                      </p>
                    )}
                  </div>

                  <div className="flex w-full items-center gap-2 sm:w-44">
                    <Input
                      type="number"
                      step="0.01"
                      placeholder="e.g. 60.00"
                      value={target.target_pct}
                      onChange={(e) => {
                        const updated = [...targetRows];
                        const current = updated[index];
                        if (current) {
                          updated[index] = {
                            ...current,
                            target_pct: e.target.value,
                          };
                          setTargetRows(updated);
                          setHasTargetsChanged(true);
                        }
                      }}
                      className={pctErr ? "border-destructive" : ""}
                    />
                    <span className="text-sm font-medium text-muted-foreground">
                      %
                    </span>
                    {pctErr && (
                      <p className="mt-1 text-xs text-destructive">
                        {pctErr.message}
                      </p>
                    )}
                  </div>

                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-9 w-9 p-0 text-muted-foreground hover:text-destructive"
                    onClick={() => {
                      const updated = targetRows.filter((_, i) => i !== index);
                      setTargetRows(updated);
                      setHasTargetsChanged(true);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span className="sr-only">Remove row</span>
                  </Button>
                </div>
              );
            })}

            {targetRows.length < 5 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  const unusedClass = VALID_ASSET_CLASSES.find(
                    (c) => !targetRows.some((r) => r.asset_class === c),
                  ) || "equity";
                  setTargetRows([
                    ...targetRows,
                    { asset_class: unusedClass, target_pct: "" },
                  ]);
                  setHasTargetsChanged(true);
                }}
                className="inline-flex items-center gap-1.5"
              >
                <PlusCircle className="h-4 w-4" />
                <span>Add Target Row</span>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Holdings / Positions Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg font-semibold">Holdings</CardTitle>
          <CardDescription>
            Current holdings derived deterministically from the transaction ledger via the average cost method.
          </CardDescription>
        </CardHeader>

        <CardContent>
          {portfolio.positions.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No holdings yet. Add buy transactions to build positions.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scheme / Fund</TableHead>
                  <TableHead>Class</TableHead>
                  <TableHead className="text-right">Units</TableHead>
                  <TableHead className="text-right">Avg Cost</TableHead>
                  <TableHead className="text-right">Invested</TableHead>
                  <TableHead className="text-right">Latest NAV</TableHead>
                  <TableHead className="text-right">Current Value</TableHead>
                  <TableHead className="text-right">Unrealized Gain</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {portfolio.positions.map((pos) => {
                  const badge = getAssetClassBadge(pos.asset_class);
                  const gain = formatGainLoss(pos.unrealized_gain);
                  return (
                    <TableRow key={pos.scheme_code}>
                      <TableCell>
                        <div className="font-medium text-foreground">
                          {pos.fund_name}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono">
                          Scheme: {pos.scheme_code}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`${badge.className} text-xs uppercase`}
                        >
                          {badge.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatUnits(pos.units)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatNav(pos.avg_nav)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatCurrency(pos.total_invested)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        <div>{formatNav(pos.latest_nav)}</div>
                        <div className="text-[10px] text-muted-foreground">
                          {pos.latest_nav_date
                            ? formatDateString(pos.latest_nav_date)
                            : ""}
                        </div>
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        {formatCurrency(pos.current_value)}
                      </TableCell>
                      <TableCell
                        className={`text-right font-mono font-medium ${
                          gain.isPositive
                            ? "text-emerald-600 dark:text-emerald-400"
                            : gain.isNegative
                              ? "text-rose-600 dark:text-rose-400"
                              : ""
                        }`}
                      >
                        {gain.formatted}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Transaction Ledger Table */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="text-lg font-semibold">
                Transaction Ledger
              </CardTitle>
              <CardDescription>
                Append-only record of all buy and sell events in chronological order.
              </CardDescription>
            </div>

            <Button
              size="sm"
              onClick={() => setIsAddTxnOpen(true)}
              className="inline-flex items-center gap-1.5"
            >
              <Plus className="h-4 w-4" />
              <span>Add Transaction</span>
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          {isTxnsLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Loading ledger...
            </div>
          ) : transactions.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No transactions recorded in this ledger yet.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Scheme / Fund</TableHead>
                  <TableHead className="text-right">Units</TableHead>
                  <TableHead className="text-right">NAV</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((txn) => (
                  <TableRow key={txn.id}>
                    <TableCell className="font-mono text-xs">
                      {formatDateString(txn.txn_date)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          txn.txn_type === "BUY"
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
                        }
                      >
                        {txn.txn_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-foreground">
                        {txn.fund_name || `Scheme ${txn.scheme_code}`}
                      </div>
                      <div className="text-[10px] text-muted-foreground font-mono">
                        {txn.scheme_code}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatUnits(txn.units)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatNav(txn.nav)}
                    </TableCell>
                    <TableCell className="text-right font-mono font-medium">
                      {formatCurrency(txn.amount)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                      {txn.notes || "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => {
                          if (
                            confirm(
                              `Delete transaction from ${txn.txn_date} (${txn.txn_type} ${txn.units} units)?`,
                            )
                          ) {
                            deleteTxnMutation.mutate(txn.id);
                          }
                        }}
                        disabled={deleteTxnMutation.isPending}
                      >
                        <Trash2 className="h-4 w-4" />
                        <span className="sr-only">Delete transaction</span>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Add Transaction Dialog */}
      <Dialog open={isAddTxnOpen} onOpenChange={setIsAddTxnOpen}>
        <DialogContent className="max-w-xl">
          <form onSubmit={handleTxnSubmit}>
            <DialogHeader>
              <DialogTitle>Record Transaction</DialogTitle>
              <DialogDescription>
                Provide any two of Units, NAV, or Amount. The third will be derived automatically.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {txnError && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>Transaction Error</AlertTitle>
                  <AlertDescription>{txnError}</AlertDescription>
                </Alert>
              )}

              {/* Fund Picker */}
              <div className="space-y-2">
                <Label htmlFor="fund-search">Mutual Fund Scheme *</Label>
                {selectedFund ? (
                  <div className="flex items-center justify-between rounded-md border border-border p-3 bg-muted/30">
                    <div>
                      <div className="font-semibold text-sm">
                        {selectedFund.name}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Scheme Code: {selectedFund.scheme_code} | Class: {selectedFund.asset_class} | Latest NAV: ₹{selectedFund.latest_nav || "—"}
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setSelectedFund(null);
                        setFundSearch("");
                      }}
                    >
                      Change
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="fund-search"
                        placeholder="Search fund name or scheme code (e.g. Parag Parikh, Nifty 50)..."
                        value={fundSearch}
                        onChange={(e) => setFundSearch(e.target.value)}
                        className="pl-9"
                      />
                    </div>

                    {isSearchingFunds && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground p-2">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Searching fund master...</span>
                      </div>
                    )}

                    {fundSearchResults?.items && fundSearchResults.items.length > 0 && (
                      <div className="max-h-48 overflow-y-auto rounded-md border border-border bg-popover shadow-md">
                        {fundSearchResults.items.map((fund) => (
                          <div
                            key={fund.scheme_code}
                            className="cursor-pointer p-2.5 text-xs hover:bg-accent border-b last:border-b-0"
                            onClick={() => {
                              setSelectedFund(fund);
                              setFundSearch("");
                            }}
                          >
                            <div className="font-medium text-foreground">
                              {fund.name}
                            </div>
                            <div className="text-[11px] text-muted-foreground">
                              {fund.scheme_code} • {fund.asset_class} • NAV: ₹{fund.latest_nav || "—"}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
                      <span>Or enter Scheme Code directly:</span>
                      <Input
                        placeholder="e.g. 122639"
                        value={manualSchemeCode}
                        onChange={(e) => setManualSchemeCode(e.target.value)}
                        className="h-7 w-32 text-xs"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Txn Type and Date */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Transaction Type *</Label>
                  <Select
                    value={txnType}
                    onValueChange={(val: "BUY" | "SELL") => setTxnType(val)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="BUY">BUY (Purchase)</SelectItem>
                      <SelectItem value="SELL">SELL (Redemption)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="txn-date">Transaction Date *</Label>
                  <Input
                    id="txn-date"
                    type="date"
                    value={txnDate}
                    onChange={(e) => setTxnDate(e.target.value)}
                    required
                  />
                </div>
              </div>

              {/* Units, NAV, Amount (Any two of three) */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="txn-units">Units</Label>
                  <Input
                    id="txn-units"
                    type="number"
                    step="0.0001"
                    placeholder={hintResult.derivedField === "units" && hintResult.derivedValue ? `[${hintResult.derivedValue}]` : "e.g. 100.5"}
                    value={txnUnits}
                    onChange={(e) => setTxnUnits(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="txn-nav">NAV (₹)</Label>
                  <Input
                    id="txn-nav"
                    type="number"
                    step="0.0001"
                    placeholder={hintResult.derivedField === "nav" && hintResult.derivedValue ? `[₹${hintResult.derivedValue}]` : "e.g. 25.25"}
                    value={txnNav}
                    onChange={(e) => setTxnNav(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="txn-amount">Total Amount (₹)</Label>
                  <Input
                    id="txn-amount"
                    type="number"
                    step="0.01"
                    placeholder={hintResult.derivedField === "amount" && hintResult.derivedValue ? `[₹${hintResult.derivedValue}]` : "e.g. 2537.63"}
                    value={txnAmount}
                    onChange={(e) => setTxnAmount(e.target.value)}
                  />
                </div>
              </div>

              {/* Hint Box */}
              {hintResult.hintMessage && (
                <div className="rounded-md bg-muted/50 p-2.5 text-xs text-muted-foreground flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <HelpCircle className="h-4 w-4 text-primary" />
                    <span>{hintResult.hintMessage}</span>
                  </div>
                  {hintResult.derivedField && hintResult.derivedValue && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={() => {
                        if (hintResult.derivedField === "amount") {
                          setTxnAmount(hintResult.derivedValue!);
                        } else if (hintResult.derivedField === "units") {
                          setTxnUnits(hintResult.derivedValue!);
                        } else if (hintResult.derivedField === "nav") {
                          setTxnNav(hintResult.derivedValue!);
                        }
                      }}
                    >
                      Apply
                    </Button>
                  )}
                </div>
              )}

              {/* Notes */}
              <div className="space-y-2">
                <Label htmlFor="txn-notes">Notes (Optional)</Label>
                <Input
                  id="txn-notes"
                  placeholder="e.g. Monthly SIP or Lump sum investment"
                  value={txnNotes}
                  onChange={(e) => setTxnNotes(e.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsAddTxnOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={addTxnMutation.isPending}>
                {addTxnMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Recording...
                  </>
                ) : (
                  "Record Transaction"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
