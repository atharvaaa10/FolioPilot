"use client";

import * as React from "react";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  Pause,
  Play,
  StopCircle,
  Trash2,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
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
import { formatDate, formatInr, formatUnits, getAssetClassBadge } from "@/lib/format";
import { sipsApi } from "@/lib/sips-api";
import type { SipDetail } from "@/lib/schemas/contract";

interface SipCardProps {
  portfolioId: string;
  sip: SipDetail;
  onViewInstallments: (sip: SipDetail) => void;
}

export function SipCard({
  portfolioId,
  sip,
  onViewInstallments,
}: SipCardProps): React.JSX.Element {
  const queryClient = useQueryClient();
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isEndOpen, setIsEndOpen] = useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["sips", portfolioId] });
    queryClient.invalidateQueries({ queryKey: ["portfolio", portfolioId] });
    queryClient.invalidateQueries({ queryKey: ["holdings", portfolioId] });
    queryClient.invalidateQueries({ queryKey: ["transactions", portfolioId] });
  };

  const pauseMutation = useMutation({
    mutationFn: () => sipsApi.pause(portfolioId, sip.id),
    onSuccess: invalidate,
  });

  const resumeMutation = useMutation({
    mutationFn: () => sipsApi.resume(portfolioId, sip.id),
    onSuccess: invalidate,
  });

  const endMutation = useMutation({
    mutationFn: () => sipsApi.end(portfolioId, sip.id),
    onSuccess: () => {
      setIsEndOpen(false);
      invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => sipsApi.delete(portfolioId, sip.id),
    onSuccess: () => {
      setIsDeleteOpen(false);
      invalidate();
    },
  });

  const classBadge = getAssetClassBadge(sip.fund.asset_class);

  // Status Badge styling
  const statusStyles: Record<string, { label: string; className: string }> = {
    active: {
      label: "Active",
      className: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
    },
    scheduled: {
      label: "Scheduled",
      className: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    },
    paused: {
      label: "Paused",
      className: "bg-amber-500/10 text-amber-600 border-amber-500/20",
    },
    ended: {
      label: "Ended",
      className: "bg-slate-500/10 text-slate-600 border-slate-500/20",
    },
  };

  const currentStatus = statusStyles[sip.status] || {
    label: sip.status,
    className: "",
  };

  const hasStepUp = parseFloat(sip.step_up_percent) > 0;

  return (
    <>
      <Card className="flex flex-col justify-between hover:shadow-sm transition-shadow">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="space-y-1">
              <CardTitle className="text-base line-clamp-1">{sip.fund.name}</CardTitle>
              <CardDescription className="text-xs flex items-center gap-2 flex-wrap">
                <span>{sip.fund.amc}</span>
                <span>•</span>
                <span className="font-mono">Scheme: {sip.fund.scheme_code}</span>
              </CardDescription>
            </div>
            <Badge variant="outline" className={`text-xs capitalize font-medium ${currentStatus.className}`}>
              {currentStatus.label}
            </Badge>
          </div>

          <div className="flex items-center gap-1.5 pt-1 flex-wrap">
            <Badge variant="outline" className={`text-[10px] ${classBadge.className}`}>
              {classBadge.label}
            </Badge>
            <Badge variant="outline" className="text-[10px] uppercase">
              {sip.fund.plan_type}
            </Badge>
            <Badge variant="outline" className="text-[10px] uppercase">
              {sip.fund.option_type}
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-3 pb-3 text-sm">
          {/* Schedule Summary */}
          <div className="grid grid-cols-2 gap-2 p-2.5 rounded-lg bg-muted/40 text-xs">
            <div>
              <div className="text-muted-foreground">Monthly Investment</div>
              <div className="font-semibold text-foreground text-sm">
                {formatInr(sip.amount)}
              </div>
              <div className="text-[11px] text-muted-foreground">
                Due on day {sip.day_of_month}
              </div>
            </div>

            <div>
              <div className="text-muted-foreground">Next Installment</div>
              {sip.next_due_date ? (
                <div>
                  <div className="font-semibold text-foreground text-sm font-mono">
                    {formatDate(sip.next_due_date)}
                  </div>
                  <div className="text-[11px] text-muted-foreground font-mono">
                    {formatInr(sip.next_installment_amount || sip.amount)}
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground italic">None scheduled</div>
              )}
            </div>
          </div>

          {/* Step-up badge */}
          {hasStepUp && (
            <div className="flex items-center gap-1 text-xs text-emerald-600 bg-emerald-50 border border-emerald-100 rounded px-2 py-1">
              <TrendingUp className="h-3.5 w-3.5" />
              <span>+{sip.step_up_percent}% annual step-up applied</span>
            </div>
          )}

          {/* Stats Summary */}
          <div className="grid grid-cols-3 gap-2 pt-1 border-t text-xs">
            <div>
              <div className="text-muted-foreground text-[11px]">Total Invested</div>
              <div className="font-medium font-mono text-xs">{formatInr(sip.stats.total_invested)}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-[11px]">Units</div>
              <div className="font-medium font-mono text-xs">{formatUnits(sip.stats.units_acquired)}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-[11px]">Installments</div>
              <div className="font-medium text-xs">
                {sip.stats.executed} / {sip.stats.installments_total}
              </div>
            </div>
          </div>

          {sip.notes && (
            <div className="text-xs text-muted-foreground italic truncate">
              &quot;{sip.notes}&quot;
            </div>
          )}
        </CardContent>

        <CardFooter className="pt-2 border-t flex items-center justify-between gap-1 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-8"
            onClick={() => onViewInstallments(sip)}
          >
            <Calendar className="h-3.5 w-3.5 mr-1" />
            Installments ({sip.stats.installments_total})
          </Button>

          <div className="flex items-center gap-1">
            {/* Pause / Resume */}
            {sip.status === "paused" ? (
              <Button
                variant="outline"
                size="sm"
                className="text-xs h-8 text-emerald-600 hover:text-emerald-700"
                onClick={() => resumeMutation.mutate()}
                disabled={resumeMutation.isPending}
                title="Resume SIP"
              >
                <Play className="h-3.5 w-3.5 mr-1" />
                Resume
              </Button>
            ) : sip.status === "active" || sip.status === "scheduled" ? (
              <Button
                variant="outline"
                size="sm"
                className="text-xs h-8 text-amber-600 hover:text-amber-700"
                onClick={() => pauseMutation.mutate()}
                disabled={pauseMutation.isPending}
                title="Pause SIP"
              >
                <Pause className="h-3.5 w-3.5 mr-1" />
                Pause
              </Button>
            ) : null}

            {/* End SIP */}
            {sip.status !== "ended" && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs h-8 text-slate-600 hover:text-slate-700"
                onClick={() => setIsEndOpen(true)}
                title="End SIP"
              >
                <StopCircle className="h-3.5 w-3.5 mr-1" />
                End
              </Button>
            )}

            {/* Delete SIP */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
              onClick={() => setIsDeleteOpen(true)}
              title="Delete SIP"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="sr-only">Delete</span>
            </Button>
          </div>
        </CardFooter>
      </Card>

      {/* End SIP Confirmation */}
      <Dialog open={isEndOpen} onOpenChange={setIsEndOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>End Systematic Investment Plan</DialogTitle>
            <DialogDescription>
              Ending this SIP will stop future installments from generating. Existing executed installments and ledger transactions are preserved.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-2">
            <Button variant="outline" size="sm" onClick={() => setIsEndOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => endMutation.mutate()}
              disabled={endMutation.isPending}
            >
              Confirm End SIP
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete SIP Confirmation */}
      <Dialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-destructive flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Delete SIP
            </DialogTitle>
            <DialogDescription className="space-y-2 pt-2">
              <p>
                Are you sure you want to delete this SIP? This removes the schedule, pending installments, and pauses.
              </p>
              <p className="font-medium text-foreground text-xs bg-muted/60 p-2.5 rounded">
                Note: Historical buy transactions already executed by this SIP will be kept in your portfolio ledger and converted to standard manual transactions.
              </p>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-2">
            <Button variant="outline" size="sm" onClick={() => setIsDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              Confirm Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
