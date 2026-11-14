"use client";

import * as React from "react";
import { useSyncExternalStore } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr, formatPercent, getAssetClassBadge } from "@/lib/format";
import type { AssetClassAllocationItem } from "@/lib/schemas/contract";

const emptySubscribe = () => () => {};

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity: "#2563eb",
  debt: "#16a34a",
  gold: "#ca8a04",
  hybrid: "#9333ea",
  other: "#64748b",
};

interface AllocationDonutProps {
  items: AssetClassAllocationItem[];
}

export function AllocationDonut({ items }: AllocationDonutProps): React.JSX.Element {
  const isMounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const chartData = React.useMemo(() => {
    return items.map((item) => {
      const normalized = (item.asset_class || "other").toLowerCase();
      const color = ASSET_CLASS_COLORS[normalized] || "#64748b";
      return {
        name: getAssetClassBadge(item.asset_class).label,
        asset_class: item.asset_class,
        value: parseFloat(item.current_value) || 0,
        current_value: item.current_value,
        percent: item.percent,
        color,
      };
    });
  }, [items]);

  if (!isMounted) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Asset Class Allocation</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-56 w-full items-center justify-center rounded-lg border border-border bg-muted/20">
            <div className="h-6 w-28 animate-pulse rounded bg-muted text-center text-xs text-muted-foreground flex items-center justify-center">
              Loading allocation...
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (items.length === 0 || chartData.every((d) => d.value === 0)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Asset Class Allocation</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-56 w-full items-center justify-center rounded-lg border border-border bg-muted/10">
            <p className="text-sm text-muted-foreground">No active allocation data.</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">Asset Class Allocation</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
          {/* Donut chart */}
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(_val: any, name: any, props: any) => [
                    `${formatInr(props.payload.current_value)} (${formatPercent(props.payload.percent)})`,
                    name,
                  ]}
                  contentStyle={{
                    backgroundColor: "hsl(var(--background))",
                    borderColor: "hsl(var(--border))",
                    borderRadius: "0.5rem",
                    fontSize: "0.875rem",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Allocation Table */}
          <div className="space-y-3">
            <div className="divide-y divide-border text-sm">
              {chartData.map((item) => (
                <div key={item.asset_class} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-3 w-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="font-medium">{item.name}</span>
                  </div>
                  <div className="text-right">
                    <span className="font-mono text-sm font-semibold">{formatInr(item.current_value)}</span>
                    <span className="text-xs text-muted-foreground ml-2">({formatPercent(item.percent)})</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
