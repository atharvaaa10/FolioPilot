"use client";

import * as React from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Calendar, Loader2, SkipForward } from "lucide-react";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatInr, formatNav, formatUnits } from "@/lib/format";
import { sipsApi } from "@/lib/sips-api";
import type { SipDetail, SipInstallment } from "@/lib/schemas/contract";

interface InstallmentsDialogProps {
  portfolioId: string;
  sip: SipDetail | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InstallmentsDialog({
  portfolioId,
  sip,
  open,
  onOpenChange,
}: InstallmentsDialogProps): React.JSX.Element {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [limit, setLimit] = useState(25);

  // Selected installment for skip confirmation
  const [skipTarget, setSkipTarget] = useState<SipInstallment | null>(null);
  const [skipError, setSkipError] = useState<string | null>(null);

  // Query installments
  const { data: installmentsData, isLoading } = useQuery({
    queryKey: ["sip_installments", portfolioId, sip?.id, statusFilter, limit],
    queryFn: () => {
      if (!sip) return null;
      return sipsApi.listInstallments(portfolioId, sip.id, {
        status: statusFilter === "all" ? undefined : statusFilter,
        limit,
        offset: 0,
      });
    },
    enabled: open && !!sip,
  });

  // Skip installment mutation
  const skipMutation = useMutation({
    mutationFn: (installmentId: string) => {
      if (!sip) throw new Error("No SIP selected");
      return sipsApi.skipInstallment(portfolioId, sip.id, installmentId);
    },
    onSuccess: () => {
      setSkipTarget(null);
      setSkipError(null);
      queryClient.invalidateQueries({ queryKey: ["sip_installments", portfolioId, sip?.id] });
      queryClient.invalidateQueries({ queryKey: ["sips", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["holdings", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["transactions", portfolioId] });
    },
    onError: (err: any) => {
      const errData = err?.response?.data?.error;
      const code = errData?.code;
      if (code === "LEDGER_INCONSISTENT") {
        setSkipError(
          "Cannot skip this installment because subsequent transactions rely on its units."
        );
      } else if (code === "INSTALLMENT_NOT_SKIPPABLE") {
        setSkipError("This installment cannot be skipped.");
      } else {
        setSkipError(errData?.message || err?.message || "Failed to skip installment.");
      }
    },
  });

  if (!sip) {
    return <></>;
  }

  const items = installmentsData?.items || [];
  const total = installmentsData?.total || 0;
  const hasMore = installmentsData?.has_more || false;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-primary" />
              SIP Installments — {sip.fund.name}
            </DialogTitle>
            <DialogDescription>
              Every installment generated for this SIP. Executed installments reflect as buy transactions in the portfolio ledger.
            </DialogDescription>
          </DialogHeader>

          {skipError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Action Error</AlertTitle>
              <AlertDescription>{skipError}</AlertDescription>
            </Alert>
          )}

          {/* Filter Tabs */}
          <div className="flex items-center justify-between border-b pb-2 pt-1">
            <div className="flex items-center gap-1">
              {(["all", "pending", "executed", "skipped"] as const).map((tab) => (
                <Button
                  key={tab}
                  type="button"
                  variant={statusFilter === tab ? "secondary" : "ghost"}
                  size="sm"
                  className="capitalize text-xs h-7"
                  onClick={() => {
                    setStatusFilter(tab);
                    setLimit(25);
                  }}
                >
                  {tab}
                  {tab === "all" && total > 0 && ` (${total})`}
                </Button>
              ))}
            </div>

            <div className="text-xs text-muted-foreground">
              Total Installments: {sip.stats.installments_total} (Executed: {sip.stats.executed})
            </div>
          </div>

          {/* Table */}
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading installments...
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground text-sm border rounded border-dashed">
              No {statusFilter === "all" ? "" : statusFilter} installments found.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="border rounded-md overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="py-2">Due Date</TableHead>
                      <TableHead className="py-2 text-right">Planned Amount</TableHead>
                      <TableHead className="py-2 text-center">Status</TableHead>
                      <TableHead className="py-2 text-center">NAV Date</TableHead>
                      <TableHead className="py-2 text-right">Units</TableHead>
                      <TableHead className="py-2 text-right">NAV</TableHead>
                      <TableHead className="py-2 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((inst) => {
                      const isExecuted = inst.status === "executed";
                      const isPending = inst.status === "pending";
                      const isSkipped = inst.status === "skipped";

                      return (
                        <TableRow key={inst.id}>
                          <TableCell className="font-mono text-xs font-medium">
                            {formatDate(inst.due_date)}
                          </TableCell>
                          <TableCell className="font-mono text-xs text-right font-medium">
                            {formatInr(inst.planned_amount)}
                          </TableCell>
                          <TableCell className="text-center">
                            {isExecuted && (
                              <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
                                Executed
                              </Badge>
                            )}
                            {isPending && (
                              <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-600 border-amber-500/20">
                                Pending
                              </Badge>
                            )}
                            {isSkipped && (
                              <Badge variant="outline" className="text-xs text-muted-foreground">
                                Skipped
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-center font-mono text-xs text-muted-foreground">
                            {inst.nav_date ? formatDate(inst.nav_date) : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {inst.transaction ? formatUnits(inst.transaction.units) : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {inst.transaction ? formatNav(inst.transaction.nav) : "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            {!isSkipped && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200"
                                onClick={() => {
                                  setSkipError(null);
                                  setSkipTarget(inst);
                                }}
                              >
                                <SkipForward className="h-3 w-3 mr-1" />
                                Skip
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>

              {hasMore && (
                <div className="flex justify-center pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setLimit((prev) => prev + 25)}
                  >
                    Load More Installments
                  </Button>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Skip Confirmation Dialog */}
      {skipTarget && (
        <Dialog open={!!skipTarget} onOpenChange={(o) => !o && setSkipTarget(null)}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-rose-600">
                <AlertCircle className="h-5 w-5" />
                Skip Installment
              </DialogTitle>
              <DialogDescription className="space-y-2 pt-2">
                <p>
                  Are you sure you want to skip the installment for{" "}
                  <strong>{formatDate(skipTarget.due_date)}</strong> (
                  {formatInr(skipTarget.planned_amount)})?
                </p>
                {skipTarget.status === "executed" && (
                  <p className="text-destructive font-medium text-xs bg-destructive/10 p-2 rounded">
                    Warning: Skipping an executed installment permanently deletes its buy transaction from the portfolio ledger.
                  </p>
                )}
              </DialogDescription>
            </DialogHeader>

            <DialogFooter className="pt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSkipTarget(null)}
                disabled={skipMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => skipMutation.mutate(skipTarget.id)}
                disabled={skipMutation.isPending}
              >
                {skipMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                    Skipping...
                  </>
                ) : (
                  "Confirm Skip"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
