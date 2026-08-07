"use client";

import * as React from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";

interface GpuUtilPoint {
  ts: string;
  gpu_util_pct: number;
}

interface GpuUtilPointWithIdx extends GpuUtilPoint {
  idx: number;
}

interface GpuUtilLineProps {
  data: GpuUtilPoint[];
  maxPoints?: number;
  className?: string;
}

export function GpuUtilLine({ data, maxPoints = 60, className }: GpuUtilLineProps) {
  const trimmed = React.useMemo<GpuUtilPointWithIdx[]>(
    () => data.slice(-maxPoints).map((d, i) => ({ ...d, idx: i })),
    [data, maxPoints]
  );

  const getLabel = (idx: number) => {
    const point = trimmed[idx];
    return point?.ts ? new Date(point.ts).toLocaleTimeString() : "";
  };

  return (
    <div className={cn("w-full h-48", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={trimmed} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis
            dataKey="idx"
            tickFormatter={getLabel}
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            interval={Math.max(1, Math.floor(trimmed.length / 6))}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "hsl(var(--popover))",
              border: "1px solid hsl(var(--border))",
              borderRadius: "6px",
            }}
            labelFormatter={(label) => {
              const idx = Number(label);
              return Number.isFinite(idx) ? getLabel(idx) : "";
            }}
            formatter={(value: any) => [typeof value === "number" ? `${value}%` : "—", "GPU Util"]}
          />
          <Line
            type="monotone"
            dataKey="gpu_util_pct"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}