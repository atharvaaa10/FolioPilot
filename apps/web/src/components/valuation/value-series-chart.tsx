"use client";

import * as React from "react";
import { useState, useSyncExternalStore } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatInr } from "@/lib/format";
import type { SeriesPoint } from "@/lib/schemas/contract";
import { getPortfolioValueSeries } from "@/lib/valuation-api";

const emptySubscribe = () => () => {};

export type RangeOption = "1m" | "6m" | "1y" | "3y" | "5y" | "max";

const RANGE_LABELS: { id: RangeOption; label: string }[] = [
  { id: "1m", label: "1M" },
  { id: "6m", label: "6M" },
  { id: "1y", label: "1Y" },
  { id: "3y", label: "3Y" },
  { id: "5y", label: "5Y" },
  { id: "max", label: "MAX" },
];

interface ValueSeriesChartProps {
  portfolioId?: string;
  initialPoints?: SeriesPoint[];
  title?: string;
}

export function ValueSeriesChart({
  portfolioId,
  initialPoints = [],
  title = "Portfolio Value Over Time",
}: ValueSeriesChartProps): React.JSX.Element {
  const isMounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const [range, setRange] = useState<RangeOption>("1y");
  const [points, setPoints] = useState<SeriesPoint[]>(initialPoints);
  const [loading, setLoading] = useState<boolean>(false);

  React.useEffect(() => {
    if (initialPoints.length > 0 && points.length === 0) {
      setPoints(initialPoints);
    }
  }, [initialPoints]);

  const handleRangeChange = async (newRange: RangeOption) => {
    setRange(newRange);
    if (!portfolioId) return;

    setLoading(true);
    try {
      const res = await getPortfolioValueSeries(portfolioId, newRange);
      setPoints(res.points);
    } catch {
      // Keep existing points on failure
    } finally {
      setLoading(false);
    }
  };

  const chartData = React.useMemo(() => {
    return points.map((p) => ({
      date: p.date,
      value: parseFloat(p.value) || 0,
      cost_basis: parseFloat(p.cost_basis) || 0,
      rawValue: p.value,
      rawCost: p.cost_basis,
    }));
  }, [points]);

  if (!isMounted) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <CardTitle className="text-base font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-72 w-full items-center justify-center rounded-lg border border-border bg-muted/20">
            <div className="h-6 w-28 animate-pulse rounded bg-muted text-center text-xs text-muted-foreground flex items-center justify-center">
              Loading chart...
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-2 sm:space-y-0 pb-4">
        <CardTitle className="text-base font-semibold">{title}</CardTitle>
        <div className="flex items-center gap-1">
          {RANGE_LABELS.map(({ id, label }) => (
            <Button
              key={id}
              variant={range === id ? "default" : "outline"}
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={() => handleRangeChange(id)}
              disabled={loading}
            >
              {label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <div className="flex h-72 w-full items-center justify-center rounded-lg border border-border bg-muted/10">
            <p className="text-sm text-muted-foreground">
              No historical valuation data available for this range.
            </p>
          </div>
        ) : (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(val) => formatDate(val)}
                  minTickGap={30}
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                  width={65}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  formatter={(_val: any, name: any, props: any) => [
                    formatInr(name === "Current Value" ? props.payload.rawValue : props.payload.rawCost),
                    name,
                  ]}
                  labelFormatter={(label) => formatDate(String(label))}
                  contentStyle={{
                    backgroundColor: "hsl(var(--background))",
                    borderColor: "hsl(var(--border))",
                    borderRadius: "0.5rem",
                    fontSize: "0.875rem",
                  }}
                />
                <Legend verticalAlign="top" height={36} />
                <Line
                  type="monotone"
                  dataKey="value"
                  name="Current Value"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5 }}
                />
                <Line
                  type="monotone"
                  dataKey="cost_basis"
                  name="Cost Basis"
                  stroke="#94a3b8"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
