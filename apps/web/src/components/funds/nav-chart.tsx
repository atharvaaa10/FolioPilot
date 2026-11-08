"use client";

import * as React from "react";
import { useMemo, useState, useSyncExternalStore } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDateString, formatNav } from "@/lib/format";
import type { NavPoint } from "@/types/funds";

interface NavChartProps {
  points: NavPoint[];
  schemeName: string;
}

type RangeOption = "1M" | "6M" | "1Y" | "3Y" | "ALL";

const emptySubscribe = () => () => {};

export function NavChart({ points, schemeName }: NavChartProps) {
  const isMounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const [selectedRange, setSelectedRange] = useState<RangeOption>("1Y");

  // Filter points based on selected range
  const filteredData = useMemo(() => {
    if (!points || points.length === 0) {
      return [];
    }

    // Points are in ascending chronological order
    const sorted = [...points].sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
    );

    if (selectedRange === "ALL") {
      return sorted.map((p) => ({
        date: p.date,
        nav: typeof p.nav === "number" ? p.nav : parseFloat(p.nav as string),
      }));
    }

    const lastItem = sorted[sorted.length - 1];
    if (!lastItem) {
      return [];
    }
    const latestDate = new Date(lastItem.date);
    const cutoffDate = new Date(latestDate);

    if (selectedRange === "1M") {
      cutoffDate.setMonth(cutoffDate.getMonth() - 1);
    } else if (selectedRange === "6M") {
      cutoffDate.setMonth(cutoffDate.getMonth() - 6);
    } else if (selectedRange === "1Y") {
      cutoffDate.setFullYear(cutoffDate.getFullYear() - 1);
    } else if (selectedRange === "3Y") {
      cutoffDate.setFullYear(cutoffDate.getFullYear() - 3);
    }

    const filtered = sorted.filter(
      (p) => new Date(p.date) >= cutoffDate,
    );

    return filtered.map((p) => ({
      date: p.date,
      nav: typeof p.nav === "number" ? p.nav : parseFloat(p.nav as string),
    }));
  }, [points, selectedRange]);

  if (!isMounted) {
    return (
      <div className="flex h-72 w-full items-center justify-center rounded-lg border border-border bg-card p-4">
        <div className="h-6 w-24 animate-pulse rounded bg-muted text-center text-xs text-muted-foreground flex items-center justify-center">
          Loading chart...
        </div>
      </div>
    );
  }

  if (filteredData.length === 0) {
    return (
      <div className="flex h-72 w-full items-center justify-center rounded-lg border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">
          No historical NAV points available for this range.
        </p>
      </div>
    );
  }

  // Calculate min and max for clean Y-axis scale
  const navValues = filteredData.map((d) => d.nav).filter((n) => !Number.isNaN(n));
  const minNav = Math.min(...navValues);
  const maxNav = Math.max(...navValues);
  const padding = (maxNav - minNav) * 0.05 || 1;
  const yDomain = [Math.floor(minNav - padding), Math.ceil(maxNav + padding)];

  return (
    <div className="w-full space-y-4 rounded-lg border border-border bg-card p-4">
      {/* Chart Header & Range Selector */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">NAV History</h3>
          <p className="text-xs text-muted-foreground">
            {filteredData.length} recorded points
          </p>
        </div>

        <div className="flex items-center space-x-1 rounded-md border border-border bg-muted/30 p-1 text-xs">
          {(["1M", "6M", "1Y", "3Y", "ALL"] as RangeOption[]).map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => setSelectedRange(range)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                selectedRange === range
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={filteredData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.2} vertical={false} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickFormatter={(d: string) => {
                const parts = d.split("-");
                return parts.length === 3 ? `${parts[2]}/${parts[1]}` : d;
              }}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              minTickGap={30}
            />
            <YAxis
              domain={yDomain}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `₹${v.toFixed(0)}`}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              width={48}
            />
            <Tooltip
              formatter={(value) => [
                formatNav(typeof value === "number" || typeof value === "string" ? value : null),
                "NAV",
              ]}
              labelFormatter={(label) =>
                formatDateString(typeof label === "string" ? label : "")
              }
              contentStyle={{
                backgroundColor: "var(--background)",
                borderColor: "var(--border)",
                borderRadius: "0.5rem",
                fontSize: "12px",
                color: "var(--foreground)",
              }}
            />
            <Line
              type="monotone"
              dataKey="nav"
              name={schemeName}
              stroke="#2563eb"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
