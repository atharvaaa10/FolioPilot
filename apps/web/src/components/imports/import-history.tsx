"use client";

import * as React from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  FileSpreadsheet,
  History,
  Loader2,
  RotateCcw,
  Trash2,
} from "lucide-react";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/format";
import { discardImport, getImportHistory, undoImport } from "@/lib/imports-api";
import type { ImportSummary } from "@/lib/schemas/contract";

interface ImportHistoryProps {
  portfolioId: string;
}

export function ImportHistory({ portfolioId }: ImportHistoryProps): React.JSX.Element {
  const queryClient = useQueryClient();

  const [undoTarget, setUndoTarget] = useState<ImportSummary | null>(null);
  const [discardTarget, setDiscardTarget] = useState<ImportSummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const {
    data: history = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["import-history", portfolioId],
    queryFn: () => getImportHistory(portfolioId),
  });

  const undoMutation = useMutation({
    mutationFn: async (importId: string) => {
      return undoImport(portfolioId, importId);
    },
    onSuccess: () => {
      setUndoTarget(null);
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["portfolio", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["holdings", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["transactions", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["import-history", portfolioId] });
    },
    onError: (err: any) => {
      setActionError(err.message || "Failed to undo import");
    },
  });

  const discardMutation = useMutation({
    mutationFn: async (importId: string) => {
      return discardImport(portfolioId, importId);
    },
    onSuccess: () => {
      setDiscardTarget(null);
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["import-history", portfolioId] });
    },
    onError: (err: any) => {
      setActionError(err.message || "Failed to discard preview");
    },
  });

  const renderStatusBadge = (status: ImportSummary["status"]) => {
    switch (status) {
      case "previewed":
        return <Badge variant="outline" className="border-amber-500 text-amber-600">Previewed</Badge>;
      case "committed":
        return <Badge className="bg-emerald-600 text-white">Committed</Badge>;
      case "undone":
        return <Badge variant="secondary">Undone</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4" />
            Import History
          </CardTitle>
        </CardHeader>
        <CardContent className="py-6 text-center text-sm text-muted-foreground flex items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading import history...
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error Loading History</AlertTitle>
        <AlertDescription>{error instanceof Error ? error.message : "Failed to load history"}</AlertDescription>
      </Alert>
    );
  }

  if (history.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4" />
            Import History
          </CardTitle>
          <CardDescription>Records of past Excel imports into this portfolio.</CardDescription>
        </CardHeader>
        <CardContent className="text-center py-6 text-sm text-muted-foreground">
          No transactions have been imported yet. Use the &ldquo;Import from Excel&rdquo; button above to import your ledger.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4" />
            Import History
          </CardTitle>
          <CardDescription>
            Audit log of Excel imports. Committed imports can be undone unless subsequent sell transactions depend on their units.
          </CardDescription>
        </CardHeader>

        {actionError && (
          <div className="px-6 pb-2">
            <Alert variant="destructive" className="py-2">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle className="text-xs">Action Failed</AlertTitle>
              <AlertDescription className="text-xs">{actionError}</AlertDescription>
            </Alert>
          </div>
        )}

        <CardContent>
          <div className="border rounded-md overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="text-xs">
                  <TableHead>Date</TableHead>
                  <TableHead>Filename</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Total Rows</TableHead>
                  <TableHead className="text-right">Committed</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="text-xs">
                {history.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{formatDate(item.previewed_at.slice(0, 10))}</TableCell>
                    <TableCell className="font-medium max-w-[200px] truncate" title={item.filename}>
                      <span className="flex items-center gap-1.5">
                        <FileSpreadsheet className="h-3.5 w-3.5 text-muted-foreground" />
                        {String(item.filename)}
                      </span>
                    </TableCell>
                    <TableCell>{renderStatusBadge(item.status)}</TableCell>
                    <TableCell className="text-right font-mono">{item.rows_total}</TableCell>
                    <TableCell className="text-right font-mono">
                      {item.status === "committed"
                        ? item.committed_count ?? item.will_import
                        : item.status === "undone"
                          ? `Undone (${item.undone_count ?? 0})`
                          : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {item.status === "committed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                          onClick={() => {
                            setActionError(null);
                            setUndoTarget(item);
                          }}
                        >
                          <RotateCcw className="h-3.5 w-3.5 mr-1" />
                          Undo
                        </Button>
                      )}
                      {item.status === "previewed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs text-muted-foreground hover:text-foreground"
                          onClick={() => {
                            setActionError(null);
                            setDiscardTarget(item);
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5 mr-1" />
                          Discard
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Undo Confirmation Dialog */}
      <Dialog open={!!undoTarget} onOpenChange={(open) => !open && setUndoTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <RotateCcw className="h-5 w-5" />
              Undo Transaction Import
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to undo the import of &ldquo;{undoTarget?.filename}&rdquo;?
            </DialogDescription>
          </DialogHeader>
          <div className="text-xs text-muted-foreground space-y-2 py-2">
            <p>
              This will remove all transactions created by this import batch from your portfolio ledger.
            </p>
            <p className="text-amber-600 dark:text-amber-400">
              Note: If subsequent sell transactions or redemptions rely on units from this import,
              the undo action will be rejected to protect ledger integrity.
            </p>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setUndoTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={undoMutation.isPending}
              onClick={() => undoTarget && undoMutation.mutate(undoTarget.id)}
            >
              {undoMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />}
              Confirm Undo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Discard Confirmation Dialog */}
      <Dialog open={!!discardTarget} onOpenChange={(open) => !open && setDiscardTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Discard Import Preview</DialogTitle>
            <DialogDescription>
              Are you sure you want to discard the active preview for &ldquo;{discardTarget?.filename}&rdquo;?
            </DialogDescription>
          </DialogHeader>
          <div className="text-xs text-muted-foreground py-2">
            This will remove the uncommitted preview records. No transactions were applied to your ledger.
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDiscardTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={discardMutation.isPending}
              onClick={() => discardTarget && discardMutation.mutate(discardTarget.id)}
            >
              {discardMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />}
              Discard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
