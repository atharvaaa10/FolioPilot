"use client";

import * as React from "react";
import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, History, Loader2 } from "lucide-react";

import { fundsApi } from "@/lib/funds-api";
import { ApiError } from "@/lib/api";
import {
  formatDateString,
  formatNav,
  getAssetClassBadge,
  getOptionBadge,
  getPlanBadge,
} from "@/lib/format";
import { NavChart } from "@/components/funds/nav-chart";
import { Button } from "@/components/ui/button";
import type {
  FundDetailResponse,
  FundNavHistoryResponse,
} from "@/types/funds";

interface PageProps {
  params: Promise<{ schemeCode: string }>;
}

export default function FundDetailPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const schemeCode = parseInt(resolvedParams.schemeCode, 10);
  const queryClient = useQueryClient();

  const [isPolling, setIsPolling] = useState(false);
  const [pollAttempts, setPollAttempts] = useState(0);
  const [pollError, setPollError] = useState<string | null>(null);
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Query Fund Details
  const {
    data: fund,
    isLoading: isFundLoading,
    error: fundError,
  } = useQuery<FundDetailResponse>({
    queryKey: ["fund-detail", schemeCode],
    queryFn: async () => fundsApi.getDetail(schemeCode),
    enabled: !Number.isNaN(schemeCode),
  });

  // 2. Query NAV History
  const {
    data: navHistory,
    isLoading: isNavLoading,
    refetch: refetchNav,
  } = useQuery<FundNavHistoryResponse>({
    queryKey: ["fund-nav", schemeCode],
    queryFn: async () => fundsApi.getNavHistory(schemeCode),
    enabled: !Number.isNaN(schemeCode),
  });

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
      }
    };
  }, []);

  // Handle "Load NAV history" tracking trigger and polling
  const handleStartTracking = async () => {
    try {
      setPollError(null);
      setIsPolling(true);
      setPollAttempts(1);

      // Trigger tracking
      await fundsApi.trackFund(schemeCode);

      // Poll every 2 seconds for up to 30 seconds (15 attempts)
      let currentAttempt = 1;
      const MAX_ATTEMPTS = 15;

      pollingTimerRef.current = setInterval(async () => {
        currentAttempt += 1;
        setPollAttempts(currentAttempt);

        const freshNav = await refetchNav();
        if (freshNav.data?.history_available) {
          if (pollingTimerRef.current) {
            clearInterval(pollingTimerRef.current);
          }
          setIsPolling(false);
          // Invalidate fund details so is_tracked updates
          queryClient.invalidateQueries({ queryKey: ["fund-detail", schemeCode] });
          return;
        }

        if (currentAttempt >= MAX_ATTEMPTS) {
          if (pollingTimerRef.current) {
            clearInterval(pollingTimerRef.current);
          }
          setIsPolling(false);
          setPollError(
            "Historical NAV backfill is taking longer than expected. Please check back shortly.",
          );
        }
      }, 2000);
    } catch (err) {
      setIsPolling(false);
      setPollError(
        err instanceof ApiError ? err.message : "Failed to initiate NAV history tracking.",
      );
    }
  };

  if (Number.isNaN(schemeCode)) {
    return (
      <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-6 text-center text-sm text-destructive">
        Invalid scheme code provided.
      </div>
    );
  }

  if (isFundLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-64 w-full animate-pulse rounded-lg border border-border bg-muted/30" />
      </div>
    );
  }

  if (fundError || !fund) {
    return (
      <div className="space-y-4">
        <Link
          href="/funds"
          className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1 h-3.5 w-3.5" />
          Back to all funds
        </Link>
        <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-6 text-center text-sm text-destructive">
          Fund not found or failed to load.
        </div>
      </div>
    );
  }

  const assetBadge = getAssetClassBadge(fund.asset_class);
  const planBadge = getPlanBadge(fund.plan_type);
  const optionBadge = getOptionBadge(fund.option_type);

  return (
    <div className="space-y-6">
      {/* Navigation and Top Bar */}
      <div>
        <Link
          href="/funds"
          className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="mr-1 h-3.5 w-3.5" />
          Back to all funds
        </Link>
      </div>

      {/* Fund Overview Card */}
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
              {fund.name}
            </h1>
            <p className="text-sm font-medium text-muted-foreground">{fund.amc}</p>
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span
                className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${assetBadge.className}`}
              >
                {assetBadge.label}
              </span>
              <span
                className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${planBadge.className}`}
              >
                {planBadge.label}
              </span>
              <span
                className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${optionBadge.className}`}
              >
                {optionBadge.label}
              </span>
              {fund.is_tracked && (
                <span className="inline-flex items-center rounded border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                  <CheckCircle2 className="mr-1 h-3 w-3" />
                  Tracked
                </span>
              )}
            </div>
          </div>

          <div className="text-left sm:text-right">
            <div className="text-xs text-muted-foreground">Latest NAV</div>
            <div className="text-2xl font-bold font-mono text-foreground">
              {formatNav(fund.latest_nav)}
            </div>
            <div className="text-xs text-muted-foreground">
              as of {formatDateString(fund.latest_nav_date)}
            </div>
          </div>
        </div>
      </div>

      {/* Historical NAV Chart / Backfill Section */}
      <div className="space-y-4">
        {isNavLoading ? (
          <div className="h-72 w-full animate-pulse rounded-lg border border-border bg-muted/30" />
        ) : navHistory?.history_available ? (
          <NavChart points={navHistory.points} schemeName={fund.name} />
        ) : (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card p-8 text-center space-y-3">
            <History className="h-10 w-10 text-muted-foreground opacity-50" />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-foreground">
                Historical NAV data is not loaded yet
              </h3>
              <p className="text-xs text-muted-foreground max-w-sm">
                Track this scheme to automatically backfill historical NAV time series from mfapi.in.
              </p>
            </div>

            {pollError && (
              <div className="rounded border border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive max-w-md">
                {pollError}
              </div>
            )}

            <Button
              onClick={handleStartTracking}
              disabled={isPolling}
              size="sm"
              className="mt-2"
            >
              {isPolling ? (
                <>
                  <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                  Fetching history... ({pollAttempts * 2}s)
                </>
              ) : (
                "Load NAV history"
              )}
            </Button>
          </div>
        )}
      </div>

      {/* Metadata & Classification Grid */}
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-foreground border-b border-border pb-3 mb-4">
          Scheme Classification & Identifiers
        </h3>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 md:grid-cols-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">AMFI Scheme Code</dt>
            <dd className="font-mono text-sm font-medium text-foreground mt-0.5">
              {fund.scheme_code}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">ISIN (Growth / Payout)</dt>
            <dd className="font-mono text-sm font-medium text-foreground mt-0.5">
              {fund.isin_growth || "—"}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">ISIN (Reinvestment)</dt>
            <dd className="font-mono text-sm font-medium text-foreground mt-0.5">
              {fund.isin_reinvest || "—"}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">SEBI Category</dt>
            <dd className="text-sm font-medium text-foreground mt-0.5">
              {fund.category_raw}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">Subcategory</dt>
            <dd className="text-sm font-medium text-foreground capitalize mt-0.5">
              {fund.sub_category ? fund.sub_category.replace(/-/g, " ") : "—"}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">Classification Source</dt>
            <dd className="text-sm font-medium text-foreground capitalize mt-0.5">
              {fund.classification_source.replace(/_/g, " ")}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">Active Status</dt>
            <dd className="text-sm font-medium text-foreground mt-0.5">
              {fund.is_active ? "Active" : "Inactive"}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-muted-foreground">Fund House</dt>
            <dd className="text-sm font-medium text-foreground mt-0.5">{fund.amc}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
