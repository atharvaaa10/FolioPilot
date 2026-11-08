"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";

export interface FilterState {
  assetClass: string;
  plan: string;
  option: string;
}

interface FundFiltersProps {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  disabled?: boolean;
}

const ASSET_CLASSES = [
  { value: "", label: "All Assets" },
  { value: "equity", label: "Equity" },
  { value: "debt", label: "Debt" },
  { value: "gold", label: "Gold" },
  { value: "hybrid", label: "Hybrid" },
  { value: "other", label: "Other" },
];

const PLANS = [
  { value: "", label: "All Plans" },
  { value: "direct", label: "Direct" },
  { value: "regular", label: "Regular" },
];

const OPTIONS = [
  { value: "", label: "All Options" },
  { value: "growth", label: "Growth" },
  { value: "idcw", label: "IDCW" },
];

export function FundFilters({
  filters,
  onChange,
  disabled = false,
}: FundFiltersProps) {
  const updateFilter = (key: keyof FilterState, val: string) => {
    onChange({
      ...filters,
      [key]: val,
    });
  };

  const hasActiveFilters =
    filters.assetClass !== "" || filters.plan !== "" || filters.option !== "";

  const clearFilters = () => {
    onChange({
      assetClass: "",
      plan: "",
      option: "",
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-3 py-2 text-sm">
      {/* Asset Class Filter */}
      <div className="flex items-center space-x-1">
        <label htmlFor="filter-asset-class" className="text-xs text-muted-foreground mr-1">
          Asset:
        </label>
        <select
          id="filter-asset-class"
          value={filters.assetClass}
          onChange={(e) => updateFilter("assetClass", e.target.value)}
          disabled={disabled}
          className="rounded-md border border-input bg-background px-2.5 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {ASSET_CLASSES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Plan Filter */}
      <div className="flex items-center space-x-1">
        <label htmlFor="filter-plan" className="text-xs text-muted-foreground mr-1">
          Plan:
        </label>
        <select
          id="filter-plan"
          value={filters.plan}
          onChange={(e) => updateFilter("plan", e.target.value)}
          disabled={disabled}
          className="rounded-md border border-input bg-background px-2.5 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {PLANS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Option Filter */}
      <div className="flex items-center space-x-1">
        <label htmlFor="filter-option" className="text-xs text-muted-foreground mr-1">
          Option:
        </label>
        <select
          id="filter-option"
          value={filters.option}
          onChange={(e) => updateFilter("option", e.target.value)}
          disabled={disabled}
          className="rounded-md border border-input bg-background px-2.5 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {hasActiveFilters && (
        <Button
          variant="ghost"
          size="sm"
          onClick={clearFilters}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
          disabled={disabled}
        >
          Clear filters
        </Button>
      )}
    </div>
  );
}
