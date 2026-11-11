"use client";

import * as React from "react";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Info,
  Loader2,
  Upload,
} from "lucide-react";

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
import { formatDate, formatInr } from "@/lib/format";
import {
  commitImport,
  downloadTemplateBlob,
  getImportRows,
  uploadImportFile,
} from "@/lib/imports-api";
import type { ImportRow, ImportSummary, ImportUploadResponse } from "@/lib/schemas/contract";

interface ImportDialogProps {
  portfolioId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

type DialogStep = "upload" | "uploading" | "preview" | "committing" | "result";
type FilterTab = "all" | "will_import" | "duplicate" | "warning" | "error";

export function ImportDialog({
  portfolioId,
  open,
  onOpenChange,
  onSuccess,
}: ImportDialogProps): React.JSX.Element {
  const queryClient = useQueryClient();

  const [step, setStep] = useState<DialogStep>("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false);

  // Preview state
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [skipInvalid, setSkipInvalid] = useState(false);
  const [hasMoreRows, setHasMoreRows] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [showConfirmCommit, setShowConfirmCommit] = useState(false);
  const [committedCount, setCommittedCount] = useState<number | null>(null);

  // Reset state when dialog is closed or reopened
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setStep("upload");
      setSelectedFile(null);
      setClientError(null);
      setSummary(null);
      setRows([]);
      setSkipInvalid(false);
      setShowConfirmCommit(false);
      setCommittedCount(null);
    }
    onOpenChange(isOpen);
  };

  const handleDownloadTemplate = async () => {
    try {
      setIsDownloadingTemplate(true);
      const blob = await downloadTemplateBlob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "foliopilot_transactions_template.xlsx";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setClientError(err instanceof Error ? err.message : "Failed to download template");
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setClientError("Please select an Excel (.xlsx) file");
      setSelectedFile(null);
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setClientError("File size exceeds 2 MB limit");
      setSelectedFile(null);
      return;
    }

    setClientError(null);
    setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setClientError("Please select an Excel (.xlsx) file");
      setSelectedFile(null);
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setClientError("File size exceeds 2 MB limit");
      setSelectedFile(null);
      return;
    }

    setClientError(null);
    setSelectedFile(file);
  };

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      return uploadImportFile(portfolioId, file);
    },
    onMutate: () => {
      setStep("uploading");
      setClientError(null);
    },
    onSuccess: (data: ImportUploadResponse) => {
      setSummary(data.import);
      setRows(data.rows);
      setHasMoreRows(data.rows.length < data.import.rows_total);
      setStep("preview");
    },
    onError: (err: any) => {
      setStep("upload");
      setClientError(err.message || "Failed to analyze import file");
    },
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!summary) throw new Error("No import preview active");
      return commitImport(portfolioId, summary.id, {
        plan_fingerprint: summary.plan_fingerprint,
        skip_invalid: skipInvalid,
      });
    },
    onMutate: () => {
      setStep("committing");
      setShowConfirmCommit(false);
      setClientError(null);
    },
    onSuccess: (updatedSummary: ImportSummary) => {
      setCommittedCount(updatedSummary.committed_count ?? summary?.will_import ?? 0);
      setStep("result");
      queryClient.invalidateQueries({ queryKey: ["portfolio", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["holdings", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["transactions", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["import-history", portfolioId] });
      onSuccess?.();
    },
    onError: (err: any) => {
      setStep("preview");
      setClientError(err.message || "Failed to commit transactions");
    },
  });

  const handleLoadMore = async () => {
    if (!summary || isLoadingMore) return;
    try {
      setIsLoadingMore(true);
      const statusFilter =
        activeTab === "all"
          ? undefined
          : activeTab === "will_import"
            ? undefined
            : activeTab;

      const res = await getImportRows(portfolioId, summary.id, {
        status: statusFilter,
        limit: 100,
        offset: rows.length,
      });

      setRows((prev) => [...prev, ...res.items]);
      setHasMoreRows(res.has_more);
    } catch (err: any) {
      setClientError(err.message || "Failed to load more rows");
    } finally {
      setIsLoadingMore(false);
    }
  };

  const filteredRows = rows.filter((r) => {
    if (activeTab === "all") return true;
    if (activeTab === "will_import") return r.status === "ok" || r.status === "warning";
    return r.status === activeTab;
  });

  const renderStatusBadge = (status: ImportRow["status"]) => {
    switch (status) {
      case "ok":
        return <Badge className="bg-emerald-600 hover:bg-emerald-700 text-white">Valid</Badge>;
      case "warning":
        return <Badge className="bg-amber-600 hover:bg-amber-700 text-white">Warning</Badge>;
      case "duplicate":
        return <Badge variant="secondary">Duplicate</Badge>;
      case "error":
        return <Badge variant="destructive">Error</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const isImportDisabled =
    !summary ||
    summary.will_import === 0 ||
    summary.blocking_errors.length > 0 ||
    (summary.rows_error > 0 && !skipInvalid);

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-primary" />
              Import Transactions from Excel
            </DialogTitle>
            <DialogDescription>
              Upload an Excel (.xlsx) file to preview, resolve duplicate transactions, and commit
              to your ledger.
            </DialogDescription>
          </DialogHeader>

          {clientError && (
            <Alert variant="destructive" className="my-2">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Import Error</AlertTitle>
              <AlertDescription>{clientError}</AlertDescription>
            </Alert>
          )}

          {/* STEP 1: UPLOAD */}
          {step === "upload" && (
            <div className="flex flex-col gap-6 py-4">
              <div className="rounded-lg border bg-muted/40 p-4 flex items-center justify-between">
                <div>
                  <h4 className="font-medium text-sm">Download Template</h4>
                  <p className="text-xs text-muted-foreground">
                    Get the pre-formatted Excel template with column instructions and data validation.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadTemplate}
                  disabled={isDownloadingTemplate}
                  className="gap-2"
                >
                  {isDownloadingTemplate ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Download Template (.xlsx)
                </Button>
              </div>

              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                className="border-2 border-dashed rounded-lg p-8 text-center flex flex-col items-center justify-center gap-3 hover:bg-muted/30 transition cursor-pointer"
                onClick={() => document.getElementById("file-input")?.click()}
              >
                <div className="rounded-full bg-primary/10 p-3 text-primary">
                  <Upload className="h-6 w-6" />
                </div>
                <div>
                  <p className="font-medium text-sm">
                    {selectedFile ? selectedFile.name : "Click to select or drag and drop your file here"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Excel (.xlsx) files up to 2 MB (max 5,000 data rows)
                  </p>
                </div>
                <input
                  id="file-input"
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </div>

              <DialogFooter className="gap-2 sm:gap-0">
                <Button variant="outline" onClick={() => handleOpenChange(false)}>
                  Cancel
                </Button>
                <Button
                  disabled={!selectedFile || uploadMutation.isPending}
                  onClick={() => selectedFile && uploadMutation.mutate(selectedFile)}
                >
                  Analyze & Preview
                </Button>
              </DialogFooter>
            </div>
          )}

          {/* STEP 2: UPLOADING */}
          {step === "uploading" && (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <div className="text-center">
                <h4 className="font-medium text-sm">Analyzing transactions...</h4>
                <p className="text-xs text-muted-foreground mt-1">
                  Parsing dates, checking funds, and scanning for duplicate records.
                </p>
              </div>
            </div>
          )}

          {/* STEP 3: PREVIEW */}
          {step === "preview" && summary && (
            <div className="flex-1 flex flex-col min-h-0 gap-4 overflow-hidden">
              {/* Summary Cards */}
              <div className="grid grid-cols-5 gap-2 text-center text-xs">
                <div className="border rounded-md p-2 bg-background">
                  <div className="text-muted-foreground">Total Rows</div>
                  <div className="text-base font-semibold">{summary.rows_total}</div>
                </div>
                <div className="border rounded-md p-2 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400">
                  <div>Will Import</div>
                  <div className="text-base font-semibold">{summary.will_import}</div>
                </div>
                <div className="border rounded-md p-2 bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-300">
                  <div>Duplicates</div>
                  <div className="text-base font-semibold">{summary.rows_duplicate}</div>
                </div>
                <div className="border rounded-md p-2 bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400">
                  <div>Warnings</div>
                  <div className="text-base font-semibold">{summary.rows_warning}</div>
                </div>
                <div className="border rounded-md p-2 bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-400">
                  <div>Errors</div>
                  <div className="text-base font-semibold">{summary.rows_error}</div>
                </div>
              </div>

              {/* Banners */}
              {summary.extra_columns && summary.extra_columns.length > 0 && (
                <Alert className="py-2">
                  <Info className="h-4 w-4" />
                  <AlertDescription className="text-xs">
                    Ignored extra columns: {summary.extra_columns.join(", ")}
                  </AlertDescription>
                </Alert>
              )}

              {summary.blocking_errors && summary.blocking_errors.length > 0 && (
                <Alert variant="destructive" className="py-2">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle className="text-xs font-semibold">Blocking Error</AlertTitle>
                  <AlertDescription className="text-xs">
                    {summary.blocking_errors.join(", ")}
                  </AlertDescription>
                </Alert>
              )}

              {/* Filter Tabs */}
              <div className="flex gap-2 border-b pb-2 text-xs">
                <Button
                  variant={activeTab === "all" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setActiveTab("all")}
                >
                  All ({summary.rows_total})
                </Button>
                <Button
                  variant={activeTab === "will_import" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setActiveTab("will_import")}
                >
                  Will Import ({summary.will_import})
                </Button>
                <Button
                  variant={activeTab === "duplicate" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setActiveTab("duplicate")}
                >
                  Duplicates ({summary.rows_duplicate})
                </Button>
                <Button
                  variant={activeTab === "warning" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setActiveTab("warning")}
                >
                  Warnings ({summary.rows_warning})
                </Button>
                <Button
                  variant={activeTab === "error" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setActiveTab("error")}
                >
                  Errors ({summary.rows_error})
                </Button>
              </div>

              {/* Preview Table */}
              <div className="flex-1 overflow-auto border rounded-md">
                <Table>
                  <TableHeader>
                    <TableRow className="text-xs">
                      <TableHead className="w-12">Row</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Fund</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-right">Units</TableHead>
                      <TableHead className="text-right">NAV</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Notes & Messages</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className="text-xs">
                    {filteredRows.map((r) => (
                      <TableRow key={r.row_number}>
                        <TableCell className="font-mono">{r.row_number}</TableCell>
                        <TableCell>{r.txn_date ? formatDate(r.txn_date) : "—"}</TableCell>
                        <TableCell className="max-w-[200px]">
                          {r.fund ? (
                            <div>
                              <div className="font-medium truncate">{r.fund.name}</div>
                              <div className="text-[10px] text-muted-foreground flex gap-1 mt-0.5">
                                <span>Code: {r.fund.scheme_code}</span>
                                {r.fund.plan_type && <span>• {r.fund.plan_type}</span>}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted-foreground truncate block">
                              {r.fund_name_in_file || "Unknown"}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="capitalize">{r.txn_type || "—"}</TableCell>
                        <TableCell className="text-right font-mono">
                          {r.units ? Number(r.units).toFixed(4) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.nav ? Number(r.nav).toFixed(4) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.amount ? formatInr(r.amount) : "—"}
                        </TableCell>
                        <TableCell>{renderStatusBadge(r.status)}</TableCell>
                        <TableCell className="max-w-[220px]">
                          {/* Plain text rendering for notes and messages */}
                          {r.notes && (
                            <div className="text-muted-foreground truncate mb-1">
                              {String(r.notes)}
                            </div>
                          )}
                          {r.messages && r.messages.length > 0 && (
                            <div className="space-y-0.5">
                              {r.messages.map((m, mIdx) => (
                                <div
                                  key={mIdx}
                                  className={`text-[11px] ${
                                    m.level === "error"
                                      ? "text-rose-600 dark:text-rose-400"
                                      : m.level === "warning"
                                        ? "text-amber-600 dark:text-amber-400"
                                        : "text-muted-foreground"
                                  }`}
                                >
                                  {m.message}
                                </div>
                              ))}
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {hasMoreRows && (
                <div className="text-center pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleLoadMore}
                    disabled={isLoadingMore}
                  >
                    {isLoadingMore && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
                    Load more rows
                  </Button>
                </div>
              )}

              {/* Error skip checkbox */}
              {summary.rows_error > 0 && (
                <div className="flex items-center gap-2 pt-2 border-t">
                  <input
                    type="checkbox"
                    id="skip-invalid-checkbox"
                    checked={skipInvalid}
                    onChange={(e) => setSkipInvalid(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <label htmlFor="skip-invalid-checkbox" className="text-xs font-medium cursor-pointer">
                    Skip {summary.rows_error} invalid rows and import the remaining{" "}
                    {summary.will_import} valid rows
                  </label>
                </div>
              )}

              <DialogFooter className="gap-2 sm:gap-0 pt-2 border-t">
                <Button variant="outline" onClick={() => setStep("upload")}>
                  Re-upload
                </Button>
                <Button
                  disabled={isImportDisabled}
                  onClick={() => setShowConfirmCommit(true)}
                >
                  Import {summary.will_import} Transactions
                </Button>
              </DialogFooter>
            </div>
          )}

          {/* STEP 4: COMMITTING */}
          {step === "committing" && (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <div className="text-center">
                <h4 className="font-medium text-sm">Applying transactions to ledger...</h4>
                <p className="text-xs text-muted-foreground mt-1">
                  Verifying ledger consistency and updating derived positions.
                </p>
              </div>
            </div>
          )}

          {/* STEP 5: RESULT */}
          {step === "result" && (
            <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
              <div className="rounded-full bg-emerald-100 dark:bg-emerald-950/50 p-3 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div>
                <h3 className="font-semibold text-lg">Import Complete!</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Successfully imported {committedCount} transactions into your portfolio ledger.
                </p>
              </div>
              <DialogFooter className="mt-4">
                <Button onClick={() => handleOpenChange(false)}>Close & View Holdings</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog before Commit */}
      <Dialog open={showConfirmCommit} onOpenChange={setShowConfirmCommit}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm Transaction Import</DialogTitle>
            <DialogDescription>
              Are you sure you want to apply {summary?.will_import} transactions to your portfolio?
              {summary?.rows_duplicate ? ` (${summary.rows_duplicate} duplicate rows will be skipped)` : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="text-xs text-muted-foreground space-y-2 py-2">
            <p>
              Imported transactions are editable and can also be undone as a batch from the Import
              History section.
            </p>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setShowConfirmCommit(false)}>
              Cancel
            </Button>
            <Button
              disabled={commitMutation.isPending}
              onClick={() => commitMutation.mutate()}
            >
              Confirm & Import
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
