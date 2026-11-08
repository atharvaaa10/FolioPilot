"use client";

import * as React from "react";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Briefcase,
  ChevronRight,
  FolderPlus,
  Loader2,
  PieChart,
  Trash2,
} from "lucide-react";

import { portfoliosApi, type PortfolioSummary } from "@/lib/portfolios-api";
import { formatDateString } from "@/lib/format";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function PortfoliosPage() {
  const queryClient = useQueryClient();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const {
    data: portfolios = [],
    isLoading,
    error,
  } = useQuery<PortfolioSummary[]>({
    queryKey: ["portfolios"],
    queryFn: portfoliosApi.list,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      portfoliosApi.create({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setIsCreateOpen(false);
      setNewName("");
      setNewDesc("");
      setFormError(null);
    },
    onError: (err: { message?: string }) => {
      setFormError(err.message || "Failed to create portfolio");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => portfoliosApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setDeletingId(null);
    },
    onError: (err: { message?: string }) => {
      alert(err.message || "Failed to delete portfolio");
      setDeletingId(null);
    },
  });

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      setFormError("Portfolio name is required");
      return;
    }
    setFormError(null);
    createMutation.mutate();
  };

  return (
    <div className="container mx-auto space-y-8 px-4 py-8 sm:px-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Portfolios</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your mutual fund portfolios, target allocations, and transaction ledgers.
          </p>
        </div>

        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <Button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center gap-2"
          >
            <FolderPlus className="h-4 w-4" />
            <span>Create Portfolio</span>
          </Button>
          <DialogContent>
            <form onSubmit={handleCreateSubmit}>
              <DialogHeader>
                <DialogTitle>Create New Portfolio</DialogTitle>
                <DialogDescription>
                  Give your portfolio a distinct name to organize your investments.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-4">
                {formError && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Error</AlertTitle>
                    <AlertDescription>{formError}</AlertDescription>
                  </Alert>
                )}

                <div className="space-y-2">
                  <Label htmlFor="portfolio-name">Portfolio Name *</Label>
                  <Input
                    id="portfolio-name"
                    placeholder="e.g. Retirement 2045 or Core Wealth"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    required
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="portfolio-desc">Description (Optional)</Label>
                  <Input
                    id="portfolio-desc"
                    placeholder="Short description of this portfolio's objective"
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                  />
                </div>
              </div>

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    "Create Portfolio"
                  )}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error Loading Portfolios</AlertTitle>
          <AlertDescription>
            {(error as { message?: string }).message || "Unable to retrieve your portfolios."}
          </AlertDescription>
        </Alert>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="h-28 bg-muted/40" />
              <CardContent className="h-20" />
            </Card>
          ))}
        </div>
      ) : portfolios.length === 0 ? (
        <Card className="border-dashed p-12 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Briefcase className="h-8 w-8" />
          </div>
          <h3 className="mt-4 text-lg font-semibold">No portfolios created yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your first portfolio to start recording transactions, tracking holdings, and configuring target allocations.
          </p>
          <Button
            onClick={() => setIsCreateOpen(true)}
            className="mt-6 inline-flex items-center gap-2"
          >
            <FolderPlus className="h-4 w-4" />
            <span>Create Portfolio</span>
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {portfolios.map((portfolio) => (
            <Card key={portfolio.id} className="flex flex-col justify-between transition-shadow hover:shadow-md">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-xl font-bold leading-tight">
                    <Link
                      href={`/portfolios/${portfolio.id}`}
                      className="hover:text-primary transition-colors"
                    >
                      {portfolio.name}
                    </Link>
                  </CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                    onClick={() => {
                      if (
                        confirm(
                          `Are you sure you want to delete portfolio "${portfolio.name}"? This action cannot be undone.`,
                        )
                      ) {
                        setDeletingId(portfolio.id);
                        deleteMutation.mutate(portfolio.id);
                      }
                    }}
                    disabled={deleteMutation.isPending && deletingId === portfolio.id}
                  >
                    {deleteMutation.isPending && deletingId === portfolio.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    <span className="sr-only">Delete portfolio</span>
                  </Button>
                </div>
                {portfolio.description && (
                  <CardDescription className="line-clamp-2 mt-1">
                    {portfolio.description}
                  </CardDescription>
                )}
              </CardHeader>

              <CardContent className="space-y-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <PieChart className="h-3.5 w-3.5" />
                  <span>
                    Targets:{" "}
                    {portfolio.targets && portfolio.targets.length > 0 ? (
                      <span className="font-medium text-foreground">
                        {portfolio.targets.length} asset class{portfolio.targets.length > 1 ? "es" : ""} configured
                      </span>
                    ) : (
                      <span className="italic">Not configured</span>
                    )}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  Created {formatDateString(portfolio.created_at.split("T")[0])}
                </div>
              </CardContent>

              <CardFooter className="border-t bg-muted/20 pt-4">
                <Link href={`/portfolios/${portfolio.id}`} className="w-full">
                  <Button variant="outline" className="w-full justify-between">
                    <span>View Holdings & Ledger</span>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
