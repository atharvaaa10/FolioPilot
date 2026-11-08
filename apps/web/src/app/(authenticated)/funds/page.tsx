"use client";

import * as React from "react";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, Search } from "lucide-react";

import { apiClient } from "@/lib/api";
import {
  formatDateString,
  formatNav,
  getAssetClassBadge,
  getOptionBadge,
  getPlanBadge,
} from "@/lib/formatters";
import { useDebounce } from "@/hooks/use-debounce";
import { FundFilters, type FilterState } from "@/components/funds/fund-filters";
import { Button } from "@/components/ui/button";
import type {
  FundSearchItem,
  FundSearchResponse,
  NavStatusResponse,
} from "@/types/funds";

const PAGE_SIZE = 20;

export default function FundsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 350);

  const [filters, setFilters] = useState<FilterState>({
    assetClass: "",
    plan: "",
    option: "",
  });

  const [offset, setOffset] = useState(0);
  const [accumulatedItems, setAccumulatedItems] = useState<FundSearchItem[]>([]);

  // Query NAV Freshness Status
  const { data: navStatus } = useQuery<NavStatusResponse>({
    queryKey: ["nav-status"],
    queryFn: async () => {
      return await apiClient<NavStatusResponse>("/api/v1/nav/status");
    },
    staleTime: 60 * 1000,
  });

  // Query Funds
  const { data: searchData, isLoading, isFetching, error } = useQuery<FundSearchResponse>({
    queryKey: [
      "funds-search",
      debouncedQuery,
      filters.assetClass,
      filters.plan,
      filters.option,
      offset,
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (debouncedQuery.trim()) {
        params.set("q", debouncedQuery.trim());
      }
      if (filters.assetClass) {
        params.set("asset_class", filters.assetClass);
      }
      if (filters.plan) {
        params.set("plan", filters.plan);
      }
      if (filters.option) {
        params.set("option", filters.option);
      }
      params.set("limit", PAGE_SIZE.toString());
      params.set("offset", offset.toString());

      const data = await apiClient<FundSearchResponse>(
        `/api/v1/funds/search?${params.toString()}`
      );

      if (offset === 0) {
        setAccumulatedItems(data.items);
      } else {
        setAccumulatedItems((prev) => [...prev, ...data.items]);
      }

      return data;
    },
    staleTime: 30 * 1000,
  });

  // Reset pagination when search or filters change
  const handleQueryChange = (val: string) => {
    setSearchQuery(val);
    setOffset(0);
  };

  const handleFilterChange = (newFilters: FilterState) => {
    setFilters(newFilters);
    setOffset(0);
  };

  const handleLoadMore = () => {
    setOffset((prev) => prev + PAGE_SIZE);
  };

  const hasMore = searchData?.has_more ?? false;
  const displayItems = offset === 0 && searchData?.items ? searchData.items : accumulatedItems;

  return (
    <div className="space-y-6">
      {/* Header and Operational Status Note */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Mutual Funds</h1>
          <p className="text-sm text-muted-foreground">
            Explore AMFI mutual funds, NAV history, and plan details.
          </p>
        </div>

        {navStatus && (
          <div
            className={`flex items-center space-x-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
              navStatus.is_stale
                ? "border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            }`}
          >
            {navStatus.is_stale ? (
              <AlertCircle className="h-3.5 w-3.5" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5" />
            )}
            <span>
              {navStatus.is_stale ? "NAV data may be stale" : "NAV data fresh"}
              {navStatus.last_success_time && (
                <> as of {formatDateString(navStatus.last_success_time.split("T")[0])}</>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Search Input and Filters */}
      <div className="space-y-3 rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by fund name, AMFI scheme code, or ISIN..."
            value={searchQuery}
            onChange={(e) => handleQueryChange(e.target.value)}
            className="w-full rounded-md border border-input bg-background pl-9 pr-4 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          {isFetching && (
            <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
          )}
        </div>

        <FundFilters filters={filters} onChange={handleFilterChange} disabled={isLoading} />
      </div>

      {/* Results Content */}
      {error ? (
        <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-6 text-center text-sm text-destructive">
          Failed to load funds. Please try again later.
        </div>
      ) : isLoading && offset === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div
              key={`skeleton-${idx}`}
              className="h-16 w-full animate-pulse rounded-md border border-border bg-muted/40"
            />
          ))}
        </div>
      ) : displayItems.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-12 text-center text-muted-foreground">
          <Search className="mx-auto h-8 w-8 opacity-40 mb-2" />
          <p className="text-sm font-medium">No mutual funds found</p>
          <p className="text-xs text-muted-foreground mt-1">
            Try adjusting your search keywords or resetting filters.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-muted/50 text-xs font-medium text-muted-foreground uppercase">
                <tr>
                  <th scope="col" className="px-4 py-3">Fund Scheme</th>
                  <th scope="col" className="px-4 py-3 hidden md:table-cell">Asset & Subcategory</th>
                  <th scope="col" className="px-4 py-3 hidden sm:table-cell">Plan / Option</th>
                  <th scope="col" className="px-4 py-3 text-right">Latest NAV</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {displayItems.map((item) => {
                  const assetBadge = getAssetClassBadge(item.asset_class);
                  const planBadge = getPlanBadge(item.plan_type);
                  const optionBadge = getOptionBadge(item.option_type);

                  return (
                    <tr
                      key={item.scheme_code}
                      className="transition-colors hover:bg-muted/30"
                    >
                      {/* Name & AMC */}
                      <td className="px-4 py-3">
                        <Link
                          href={`/funds/${item.scheme_code}`}
                          className="font-medium text-foreground hover:text-primary transition-colors line-clamp-1"
                        >
                          {item.name}
                        </Link>
                        <div className="flex items-center space-x-2 mt-0.5 text-xs text-muted-foreground">
                          <span>{item.amc}</span>
                          <span>•</span>
                          <span className="font-mono">{item.scheme_code}</span>
                        </div>
                      </td>

                      {/* Asset Class & Subcategory */}
                      <td className="px-4 py-3 hidden md:table-cell">
                        <div className="flex flex-col items-start gap-1">
                          <span
                            className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold ${assetBadge.className}`}
                          >
                            {assetBadge.label}
                          </span>
                          {item.sub_category && (
                            <span className="text-xs text-muted-foreground capitalize">
                              {item.sub_category.replace(/-/g, " ")}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Plan & Option */}
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${planBadge.className}`}
                          >
                            {planBadge.label}
                          </span>
                          <span
                            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${optionBadge.className}`}
                          >
                            {optionBadge.label}
                          </span>
                        </div>
                      </td>

                      {/* Latest NAV */}
                      <td className="px-4 py-3 text-right">
                        <div className="font-mono font-semibold text-foreground">
                          {formatNav(item.latest_nav)}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {formatDateString(item.latest_nav_date)}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination: Load More */}
          {hasMore && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadMore}
                disabled={isFetching}
                className="min-w-32"
              >
                {isFetching ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Loading...
                  </>
                ) : (
                  "Load more"
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
