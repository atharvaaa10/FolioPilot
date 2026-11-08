"use client";

import * as React from "react";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Edit2,
  HelpCircle,
  Loader2,
  Plus,
  PlusCircle,
  Search,
  Trash2,
} from "lucide-react";

import {
  portfoliosApi,
  type CreateTransactionPayload,
  type HoldingsResponse,
  type PortfolioDetail,
  type TargetAllocation,
  type TransactionItem,
  type UpdateTransactionPayload,
} from "@/lib/portfolios-api";
import {
  formatDate,
  formatInr,
  formatUnits,
  getAssetClassBadge,
  getTodayIsoDate,
} from "@/lib/format";
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
  const todayIso = getTodayIsoDate();

  // Portfolio Detail Query
  const {
    data: portfolio,
    isLoading: isPortfolioLoading,
    error: portfolioError,
  } = useQuery<PortfolioDetail>({
    queryKey: ["portfolio", id],
    queryFn: () => portfoliosApi.get(id),
  });

  // Holdings Query (Phase 3A derived positions)
  const {
    data: holdingsData,
    isLoading: isHoldingsLoading,
  } = useQuery<HoldingsResponse>({
    queryKey: ["holdings", id],
    queryFn: () => portfoliosApi.getHoldings(id),
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

  // Sync initial targets
  useEffect(() => {
    if (portfolio?.targets) {
      setTargetRows(portfolio.targets);
    }
  }, [portfolio?.targets]);

  const targetsEvaluation = evaluateTargets(targetRows);

  const updateTargetsMutation = useMutation({
    mutationFn: (newTargets: TargetAllocation[]) =>
      portfoliosApi.updateTargets(id, newTargets),
    onSuccess: (savedTargets) => {
      setTargetRows(savedTargets);
      setHasTargetsChanged(false);
      setTargetsMessage("Target allocations updated successfully.");
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      setTimeout(() => setTargetsMessage(null), 3000);
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
  const [txnDate, setTxnDate] = useState(todayIso);
  const [txnUnits, setTxnUnits] = useState("");
  const [txnNav, setTxnNav] = useState("");
  const [txnAmount, setTxnAmount] = useState("");
  const [txnNotes, setTxnNotes] = useState("");
  const [txnError, setTxnError] = useState<string | null>(null);

  // Edit Transaction Modal State
  const [isEditTxnOpen, setIsEditTxnOpen] = useState(false);
  const [editingTxn, setEditingTxn] = useState<TransactionItem | null>(null);
  const [editDate, setEditDate] = useState("");
  const [editUnits, setEditUnits] = useState("");
  const [editNav, setEditNav] = useState("");
  const [editAmount, setEditAmount] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  // Fund search dropdown query
  const { data: searchResults, isLoading: isSearchingFunds } =
    useQuery<FundSearchResponse>({
      queryKey: ["fund-picker", debouncedFundSearch],
      queryFn: () =>
        apiClient<FundSearchResponse>(
          `/api/v1/funds/search?q=${encodeURIComponent(debouncedFundSearch)}&limit=8`,
        ),
      enabled: isAddTxnOpen && debouncedFundSearch.trim().length >= 2,
    });

  // Calculate live derivation hints for Add
  const hintResult = deriveTransactionValues({
    units: txnUnits,
    nav: txnNav,
    amount: txnAmount,
  });

  // Calculate live derivation hints for Edit
  const editHintResult = deriveTransactionValues({
    units: editUnits,
    nav: editNav,
    amount: editAmount,
  });

  // Auto-fill NAV when fund is selected if user hasn't typed one
  useEffect(() => {
    if (
      selectedFund &&
      selectedFund.latest_nav !== null &&
      selectedFund.latest_nav !== undefined &&
      !txnNav
    ) {
      setTxnNav(String(selectedFund.latest_nav));
    }
  }, [selectedFund, txnNav]);

  const addTxnMutation = useMutation({
    mutationFn: (payload: CreateTransactionPayload) =>
      portfoliosApi.createTransaction(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      queryClient.invalidateQueries({ queryKey: ["holdings", id] });
      queryClient.invalidateQueries({ queryKey: ["transactions", id] });
      setIsAddTxnOpen(false);
      resetTxnForm();
    },
    onError: (err: { message?: string }) => {
      setTxnError(err.message || "Failed to record transaction.");
    },
  });

  const updateTxnMutation = useMutation({
    mutationFn: (payload: UpdateTransactionPayload) => {
      if (!editingTxn) throw new Error("No transaction selected for edit");
      return portfoliosApi.updateTransaction(id, editingTxn.id, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      queryClient.invalidateQueries({ queryKey: ["holdings", id] });
      queryClient.invalidateQueries({ queryKey: ["transactions", id] });
      setIsEditTxnOpen(false);
      setEditingTxn(null);
    },
    onError: (err: { message?: string }) => {
      setEditError(err.message || "Failed to update transaction.");
    },
  });

  const deleteTxnMutation = useMutation({
    mutationFn: (txnId: string) => portfoliosApi.deleteTransaction(id, txnId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", id] });
      queryClient.invalidateQueries({ queryKey: ["holdings", id] });
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
    setTxnDate(todayIso);
    setTxnUnits("");
    setTxnNav("");
    setTxnAmount("");
    setTxnNotes("");
    setTxnError(null);
  };

  const openEditModal = (txn: TransactionItem) => {
    setEditingTxn(txn);
    setEditDate(txn.txn_date);
    setEditUnits(txn.units);
    setEditNav(txn.nav);
    setEditAmount(txn.amount);
    setEditNotes(txn.notes || "");
    setEditError(null);
    setIsEditTxnOpen(true);
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

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTxn) return;
    setEditError(null);

    if (!editDate) {
      setEditError("Transaction date is required.");
      return;
    }

    const filledCount = [editUnits, editNav, editAmount].filter(
      (v) => v.trim() !== "",
    ).length;

    if (filledCount < 2) {
      setEditError("Please fill at least two of Units, NAV, and Amount.");
      return;
    }

    if (!editHintResult.isValid) {
      setEditError(editHintResult.error || "Invalid transaction values.");
      return;
    }

    let finalUnits = editUnits.trim() || undefined;
    let finalNav = editNav.trim() || undefined;
    let finalAmount = editAmount.trim() || undefined;

    if (editHintResult.derivedField === "amount" && editHintResult.derivedValue) {
      finalAmount = editHintResult.derivedValue;
    } else if (editHintResult.derivedField === "units" && editHintResult.derivedValue) {
      finalUnits = editHintResult.derivedValue;
    } else if (editHintResult.derivedField === "nav" && editHintResult.derivedValue) {
      finalNav = editHintResult.derivedValue;
    }

    updateTxnMutation.mutate({
      txn_date: editDate,
      units: finalUnits,
      nav: finalNav,
      amount: finalAmount,
      notes: editNotes.trim() || undefined,
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

  const holdings = holdingsData?.items || [];
  const totals = holdingsData?.totals;

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

      {/* Summary Metrics Cards (Phase 3A: No Valuation) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Total cost basis
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {formatInr(totals?.cost_basis || portfolio.total_cost_basis || "0.00")}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Aggregate cost basis across open positions
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Open positions
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {totals?.open_positions ?? portfolio.open_positions ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Funds currently held with positive units
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase font-medium">
              Transactions
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {portfolio.total_transactions ?? transactions.length}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Total ledger entries recorded
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
                  const unusedClass =
                    VALID_ASSET_CLASSES.find(
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

      {/* Holdings Table (Average Cost Derived Positions) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg font-semibold">Holdings</CardTitle>
          <CardDescription>
            Positions derived deterministically from the transaction ledger via the average cost method.
          </CardDescription>
        </CardHeader>

        <CardContent>
          {isHoldingsLoading ? (
            <div className="flex h-32 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : holdings.length === 0 ? (
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
                  <TableHead className="text-right">Cost Basis</TableHead>
                  <TableHead className="text-right">Total Bought</TableHead>
                  <TableHead className="text-right">Total Sold</TableHead>
                  <TableHead className="text-center">Dates (First - Last)</TableHead>
                  <TableHead className="text-center">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {holdings.map((h) => {
                  const badge = getAssetClassBadge(h.fund.asset_class);
                  return (
                    <TableRow key={h.scheme_code}>
                      <TableCell>
                        <div className="font-medium text-foreground">
                          {h.fund.name}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono">
                          Scheme: {h.scheme_code}
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
                        {formatUnits(h.units)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatInr(h.avg_cost)}
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        {formatInr(h.cost_basis)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {formatInr(h.total_bought)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {formatInr(h.total_sold)}
                      </TableCell>
                      <TableCell className="text-center text-xs text-muted-foreground">
                        {formatDate(h.first_txn_date)} - {formatDate(h.last_txn_date)}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant={h.is_closed ? "secondary" : "default"}>
                          {h.is_closed ? "Closed" : "Open"}
                        </Badge>
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
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg font-semibold">
                Transaction Ledger
              </CardTitle>
              <CardDescription>
                Deterministic append-only ledger entries ordered by transaction date.
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {isTxnsLoading ? (
            <div className="flex h-32 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : transactions.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No transactions recorded yet. Click &quot;Add Transaction&quot; to begin.
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
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((txn) => (
                  <TableRow key={txn.id}>
                    <TableCell className="font-mono text-xs whitespace-nowrap">
                      {formatDate(txn.txn_date)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          txn.txn_type === "BUY"
                            ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-600 border-rose-500/20"
                        }
                      >
                        {txn.txn_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">
                        {txn.fund_name || `Scheme ${txn.scheme_code || "Unknown"}`}
                      </div>
                      {txn.scheme_code && (
                        <div className="text-xs text-muted-foreground font-mono">
                          {txn.scheme_code}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatUnits(txn.units)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      ₹{txn.nav}
                    </TableCell>
                    <TableCell className="text-right font-mono font-medium">
                      {formatInr(txn.amount)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                      {txn.notes || "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          title="Edit transaction"
                          onClick={() => openEditModal(txn)}
                        >
                          <Edit2 className="h-4 w-4" />
                          <span className="sr-only">Edit</span>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                          title="Delete transaction"
                          disabled={deleteTxnMutation.isPending}
                          onClick={() => {
                            if (
                              confirm(
                                "Are you sure you want to delete this transaction?",
                              )
                            ) {
                              deleteTxnMutation.mutate(txn.id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                          <span className="sr-only">Delete</span>
                        </Button>
                      </div>
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add Transaction</DialogTitle>
            <DialogDescription>
              Record a buy or sell transaction. You may fill any two of Units, NAV, or Amount, and FolioPilot will derive the third.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleTxnSubmit} className="space-y-4 py-2">
            {txnError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{txnError}</AlertDescription>
              </Alert>
            )}

            {/* Fund Selector */}
            <div className="space-y-2">
              <Label>Mutual Fund Scheme</Label>
              {selectedFund ? (
                <div className="flex items-center justify-between rounded-md border p-2 text-sm bg-muted/40">
                  <div>
                    <p className="font-medium">{selectedFund.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Scheme Code: {selectedFund.scheme_code} • {selectedFund.amc}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedFund(null)}
                  >
                    Change
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      type="text"
                      placeholder="Search scheme name or AMFI code..."
                      value={fundSearch}
                      onChange={(e) => setFundSearch(e.target.value)}
                      className="pl-9"
                    />
                  </div>

                  {isSearchingFunds && (
                    <div className="py-2 text-center text-xs text-muted-foreground flex items-center justify-center gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" /> Searching...
                    </div>
                  )}

                  {searchResults && searchResults.items.length > 0 && (
                    <div className="max-h-48 overflow-y-auto rounded-md border bg-popover text-popover-foreground shadow-sm divide-y">
                      {searchResults.items.map((fund) => (
                        <button
                          key={fund.scheme_code}
                          type="button"
                          className="w-full text-left p-2 hover:bg-muted text-xs transition-colors"
                          onClick={() => {
                            setSelectedFund(fund);
                            setFundSearch("");
                          }}
                        >
                          <div className="font-medium text-foreground">
                            {fund.name}
                          </div>
                          <div className="text-muted-foreground">
                            AMFI: {fund.scheme_code} • {fund.amc}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="pt-1">
                    <Label className="text-xs text-muted-foreground">
                      Or enter scheme code directly:
                    </Label>
                    <Input
                      type="number"
                      placeholder="e.g. 122639"
                      value={manualSchemeCode}
                      onChange={(e) => setManualSchemeCode(e.target.value)}
                      className="mt-1"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Type & Date */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Transaction Type</Label>
                <Select
                  value={txnType}
                  onValueChange={(val: "BUY" | "SELL") => setTxnType(val)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="BUY">BUY</SelectItem>
                    <SelectItem value="SELL">SELL</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Date</Label>
                <Input
                  type="date"
                  value={txnDate}
                  max={todayIso}
                  onChange={(e) => setTxnDate(e.target.value)}
                  required
                />
              </div>
            </div>

            {/* Math Inputs: Any 2 of 3 */}
            <div className="space-y-3 rounded-lg border p-3 bg-muted/20">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="font-medium text-foreground">
                  Transaction Values
                </span>
                <span className="flex items-center gap-1">
                  <HelpCircle className="h-3.5 w-3.5" /> Any two required
                </span>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Units</Label>
                  <Input
                    type="number"
                    step="0.0001"
                    placeholder="0.0000"
                    value={txnUnits}
                    onChange={(e) => setTxnUnits(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">NAV (₹)</Label>
                  <Input
                    type="number"
                    step="0.00000001"
                    placeholder="0.0000"
                    value={txnNav}
                    onChange={(e) => setTxnNav(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Amount (₹)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                    value={txnAmount}
                    onChange={(e) => setTxnAmount(e.target.value)}
                  />
                </div>
              </div>

              {/* Dynamic Live Hint */}
              {hintResult.hintMessage && (
                <div
                  className={`text-xs p-2 rounded ${
                    hintResult.isValid
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "bg-destructive/10 text-destructive"
                  }`}
                >
                  {hintResult.hintMessage}
                </div>
              )}
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label>Notes (Optional)</Label>
              <Input
                type="text"
                placeholder="e.g. Monthly SIP or Rebalancing"
                value={txnNotes}
                onChange={(e) => setTxnNotes(e.target.value)}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsAddTxnOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={addTxnMutation.isPending || !hintResult.isValid}
              >
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

      {/* Edit Transaction Dialog */}
      <Dialog open={isEditTxnOpen} onOpenChange={setIsEditTxnOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit Transaction</DialogTitle>
            <DialogDescription>
              Update transaction details. Date, units, NAV, amount, and notes may be edited under full ledger re-validation.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleEditSubmit} className="space-y-4 py-2">
            {editError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{editError}</AlertDescription>
              </Alert>
            )}

            {/* Read-only Fund & Type */}
            <div className="rounded-md border p-3 bg-muted/40 text-xs space-y-1">
              <p className="font-medium text-foreground">
                {editingTxn?.fund_name || `Scheme ${editingTxn?.scheme_code}`}
              </p>
              <p className="text-muted-foreground">
                Type: <span className="font-semibold">{editingTxn?.txn_type}</span> (Immutable)
              </p>
            </div>

            {/* Date */}
            <div className="space-y-2">
              <Label>Date</Label>
              <Input
                type="date"
                value={editDate}
                max={todayIso}
                onChange={(e) => setEditDate(e.target.value)}
                required
              />
            </div>

            {/* Math Inputs: Any 2 of 3 */}
            <div className="space-y-3 rounded-lg border p-3 bg-muted/20">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="font-medium text-foreground">
                  Transaction Values
                </span>
                <span className="flex items-center gap-1">
                  <HelpCircle className="h-3.5 w-3.5" /> Any two required
                </span>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Units</Label>
                  <Input
                    type="number"
                    step="0.0001"
                    placeholder="0.0000"
                    value={editUnits}
                    onChange={(e) => setEditUnits(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">NAV (₹)</Label>
                  <Input
                    type="number"
                    step="0.00000001"
                    placeholder="0.0000"
                    value={editNav}
                    onChange={(e) => setEditNav(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Amount (₹)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                    value={editAmount}
                    onChange={(e) => setEditAmount(e.target.value)}
                  />
                </div>
              </div>

              {/* Dynamic Live Hint */}
              {editHintResult.hintMessage && (
                <div
                  className={`text-xs p-2 rounded ${
                    editHintResult.isValid
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "bg-destructive/10 text-destructive"
                  }`}
                >
                  {editHintResult.hintMessage}
                </div>
              )}
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label>Notes (Optional)</Label>
              <Input
                type="text"
                placeholder="Notes..."
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsEditTxnOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={updateTxnMutation.isPending || !editHintResult.isValid}
              >
                {updateTxnMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving Changes...
                  </>
                ) : (
                  "Save Changes"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
