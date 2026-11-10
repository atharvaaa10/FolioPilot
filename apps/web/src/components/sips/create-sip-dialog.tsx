"use client";

import * as React from "react";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Calendar, Loader2, Search, TrendingUp } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebounce } from "@/hooks/use-debounce";
import { fundsApi } from "@/lib/funds-api";
import { formatDate, formatInr, getTodayIsoDate } from "@/lib/format";
import { sipsApi, type CreateSipPayload } from "@/lib/sips-api";
import type { SipPreviewItem } from "@/lib/schemas/contract";
import type { FundSearchItem } from "@/types/funds";

export interface SelectedFundInfo {
  scheme_code: number;
  name: string;
  amc?: string;
  plan_type?: string;
  option_type?: string;
}

interface CreateSipDialogProps {
  portfolioId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  initialFund?: SelectedFundInfo;
}

export function CreateSipDialog({
  portfolioId,
  open,
  onOpenChange,
  onSuccess,
  initialFund,
}: CreateSipDialogProps): React.JSX.Element {
  const queryClient = useQueryClient();
  const todayIso = getTodayIsoDate();

  // Selected Fund
  const [selectedFund, setSelectedFund] = useState<SelectedFundInfo | null>(
    initialFund || null
  );

  // Fund search state
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearch = useDebounce(searchQuery, 300);
  const [searchResults, setSearchResults] = useState<FundSearchItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Form Fields
  const [amount, setAmount] = useState("5000");
  const [dayOfMonth, setDayOfMonth] = useState<number>(10);
  const [startDate, setStartDate] = useState(todayIso);
  const [endDate, setEndDate] = useState("");
  const [stepUpPercent, setStepUpPercent] = useState("0");
  const [notes, setNotes] = useState("");

  // Validation & Error
  const [formError, setFormError] = useState<string | null>(null);

  // Real-time Preview state
  const [previewItems, setPreviewItems] = useState<SipPreviewItem[]>([]);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Debounced values for preview
  const debouncedAmount = useDebounce(amount, 350);
  const debouncedDay = useDebounce(dayOfMonth, 350);
  const debouncedStart = useDebounce(startDate, 350);
  const debouncedEnd = useDebounce(endDate, 350);
  const debouncedStepUp = useDebounce(stepUpPercent, 350);

  // Fund search effect
  useEffect(() => {
    if (!debouncedSearch || debouncedSearch.length < 2) {
      setSearchResults([]);
      return;
    }

    let active = true;
    setIsSearching(true);
    const searchParams = new URLSearchParams({ q: debouncedSearch, limit: "8" });
    fundsApi
      .searchFunds(searchParams)
      .then((res) => {
        if (active) {
          setSearchResults(res.items);
        }
      })
      .catch(() => {
        if (active) setSearchResults([]);
      })
      .finally(() => {
        if (active) setIsSearching(false);
      });

    return () => {
      active = false;
    };
  }, [debouncedSearch]);

  // Real-time Preview effect
  useEffect(() => {
    if (!open) return;
    if (!selectedFund) {
      setPreviewItems([]);
      setPreviewError(null);
      return;
    }

    const parsedAmt = parseFloat(debouncedAmount);
    if (isNaN(parsedAmt) || parsedAmt < 100 || parsedAmt > 10000000) {
      setPreviewItems([]);
      return;
    }

    if (!debouncedDay || debouncedDay < 1 || debouncedDay > 28) {
      setPreviewItems([]);
      return;
    }

    if (!debouncedStart) {
      setPreviewItems([]);
      return;
    }

    let active = true;
    setIsPreviewLoading(true);
    setPreviewError(null);

    const payload: CreateSipPayload = {
      scheme_code: selectedFund.scheme_code,
      amount: debouncedAmount,
      day_of_month: debouncedDay,
      start_date: debouncedStart,
      end_date: debouncedEnd ? debouncedEnd : null,
      step_up_percent: debouncedStepUp || "0",
    };

    sipsApi
      .preview(portfolioId, payload, 12)
      .then((res) => {
        if (active) {
          setPreviewItems(res.items);
          setPreviewError(null);
        }
      })
      .catch((err: any) => {
        if (active) {
          setPreviewItems([]);
          const msg =
            err?.response?.data?.error?.message ||
            err?.message ||
            "Unable to generate schedule preview";
          setPreviewError(msg);
        }
      })
      .finally(() => {
        if (active) setIsPreviewLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    open,
    portfolioId,
    selectedFund,
    debouncedAmount,
    debouncedDay,
    debouncedStart,
    debouncedEnd,
    debouncedStepUp,
  ]);

  // Create SIP mutation
  const createMutation = useMutation({
    mutationFn: (payload: CreateSipPayload) => sipsApi.create(portfolioId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sips", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["portfolio", portfolioId] });
      onOpenChange(false);
      onSuccess?.();
    },
    onError: (err: any) => {
      const errData = err?.response?.data?.error;
      const code = errData?.code;
      if (code === "FUND_INACTIVE") {
        setFormError("The selected fund is inactive and cannot accept new investments.");
      } else if (code === "SIP_LIMIT_REACHED") {
        setFormError("This portfolio has reached the maximum limit of 50 SIPs.");
      } else if (code === "SIP_INVALID_SCHEDULE") {
        setFormError(
          errData?.message || "The schedule has no valid execution dates within the range."
        );
      } else {
        setFormError(errData?.message || err?.message || "Failed to create SIP.");
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!selectedFund) {
      setFormError("Please select a mutual fund.");
      return;
    }

    const parsedAmt = parseFloat(amount);
    if (isNaN(parsedAmt) || parsedAmt < 100 || parsedAmt > 10000000) {
      setFormError("Amount must be between ₹100 and ₹10,000,000.");
      return;
    }

    if (!dayOfMonth || dayOfMonth < 1 || dayOfMonth > 28) {
      setFormError("Day of month must be between 1 and 28.");
      return;
    }

    if (!startDate) {
      setFormError("Start date is required.");
      return;
    }

    if (endDate && endDate < startDate) {
      setFormError("End date cannot precede start date.");
      return;
    }

    const parsedStepUp = parseFloat(stepUpPercent);
    if (isNaN(parsedStepUp) || parsedStepUp < 0 || parsedStepUp > 100) {
      setFormError("Step-up percent must be between 0 and 100%.");
      return;
    }

    createMutation.mutate({
      scheme_code: selectedFund.scheme_code,
      amount,
      day_of_month: dayOfMonth,
      start_date: startDate,
      end_date: endDate ? endDate : null,
      step_up_percent: stepUpPercent || "0",
      notes: notes.trim() ? notes.trim() : null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-primary" />
            Create Systematic Investment Plan (SIP)
          </DialogTitle>
          <DialogDescription>
            Automate monthly investments into mutual funds with schedule preview and optional annual step-up.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          {formError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Validation Error</AlertTitle>
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}

          {/* Fund Selection */}
          <div className="space-y-2">
            <Label>Mutual Fund</Label>
            {selectedFund ? (
              <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/30">
                <div className="space-y-1">
                  <div className="font-medium text-sm">{selectedFund.name}</div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {selectedFund.amc && <span>{selectedFund.amc}</span>}
                    <span>•</span>
                    <span className="font-mono">Scheme: {selectedFund.scheme_code}</span>
                    {selectedFund.plan_type && (
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {selectedFund.plan_type} {selectedFund.option_type || ""}
                      </Badge>
                    )}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedFund(null)}
                >
                  Change
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search by fund name or scheme code..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                  {isSearching && (
                    <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                </div>

                {searchResults.length > 0 && (
                  <div className="border rounded-md divide-y max-h-48 overflow-y-auto bg-popover">
                    {searchResults.map((f) => (
                      <div
                        key={f.scheme_code}
                        className="p-2.5 hover:bg-muted/50 cursor-pointer flex items-center justify-between text-sm transition-colors"
                        onClick={() => {
                          setSelectedFund({
                            scheme_code: f.scheme_code,
                            name: f.name,
                            amc: f.amc,
                            plan_type: f.plan_type,
                            option_type: f.option_type,
                          });
                          setSearchQuery("");
                          setSearchResults([]);
                        }}
                      >
                        <div>
                          <div className="font-medium text-xs">{f.name}</div>
                          <div className="text-[11px] text-muted-foreground">
                            {f.amc} • Scheme: {f.scheme_code}
                          </div>
                        </div>
                        <Badge variant="outline" className="text-[10px] uppercase">
                          {f.plan_type}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Amount & Day of Month */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sip-amount">Monthly Amount (₹)</Label>
              <Input
                id="sip-amount"
                type="number"
                min="100"
                max="10000000"
                step="1"
                placeholder="5000"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
              <span className="text-xs text-muted-foreground">Min ₹100, Max ₹1,00,00,000</span>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sip-day">Day of Month (1 - 28)</Label>
              <Input
                id="sip-day"
                type="number"
                min="1"
                max="28"
                placeholder="10"
                value={dayOfMonth}
                onChange={(e) => setDayOfMonth(parseInt(e.target.value, 10) || 1)}
                required
              />
              <span className="text-xs text-muted-foreground">Due on this day every month</span>
            </div>
          </div>

          {/* Start Date & End Date */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sip-start">Start Date</Label>
              <Input
                id="sip-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
              <span className="text-xs text-muted-foreground">Can be up to 1 year ahead</span>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sip-end">End Date (Optional)</Label>
              <Input
                id="sip-end"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                min={startDate || todayIso}
              />
              <span className="text-xs text-muted-foreground">Leave empty for perpetual SIP</span>
            </div>
          </div>

          {/* Annual Step-up & Notes */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sip-stepup" className="flex items-center gap-1.5">
                <TrendingUp className="h-4 w-4 text-emerald-500" />
                Annual Step-up (%)
              </Label>
              <Input
                id="sip-stepup"
                type="number"
                min="0"
                max="100"
                step="0.5"
                placeholder="0"
                value={stepUpPercent}
                onChange={(e) => setStepUpPercent(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">Increases after every 12 installments</span>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sip-notes">Notes (Optional)</Label>
              <Input
                id="sip-notes"
                placeholder="e.g. Retirement goal, tax saver"
                maxLength={200}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">Max 200 characters</span>
            </div>
          </div>

          {/* Schedule Preview Section */}
          <div className="pt-2 border-t">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Live Schedule Preview
              </div>
              {isPreviewLoading && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Updating...
                </div>
              )}
            </div>

            {previewError ? (
              <div className="text-xs text-destructive p-2 rounded bg-destructive/10">
                {previewError}
              </div>
            ) : previewItems.length > 0 ? (
              <div className="border rounded-md max-h-48 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="py-1 text-xs">#</TableHead>
                      <TableHead className="py-1 text-xs">Due Date</TableHead>
                      <TableHead className="py-1 text-xs text-right">Planned Amount</TableHead>
                      <TableHead className="py-1 text-xs text-right">Step-up</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewItems.map((item, idx) => {
                      const isFirst = idx === 0;
                      const prevItem = previewItems[idx - 1];
                      const hasIncrease =
                        !isFirst &&
                        prevItem !== undefined &&
                        parseFloat(item.planned_amount) > parseFloat(prevItem.planned_amount);

                      return (
                        <TableRow
                          key={item.due_date}
                          className={hasIncrease ? "bg-emerald-500/5 font-medium" : ""}
                        >
                          <TableCell className="py-1 font-mono text-xs">{idx + 1}</TableCell>
                          <TableCell className="py-1 font-mono text-xs">
                            {formatDate(item.due_date)}
                          </TableCell>
                          <TableCell className="py-1 font-mono text-xs text-right font-medium">
                            {formatInr(item.planned_amount)}
                          </TableCell>
                          <TableCell className="py-1 text-xs text-right">
                            {hasIncrease ? (
                              <Badge variant="outline" className="text-[10px] text-emerald-600 bg-emerald-50 border-emerald-200">
                                +{stepUpPercent}%
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground text-center py-4 border rounded border-dashed">
                Select a mutual fund and valid details to see the projected schedule.
              </div>
            )}
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || !selectedFund}>
              {createMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating SIP...
                </>
              ) : (
                "Create SIP"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
