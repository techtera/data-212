"use client";

import * as React from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";

interface EpochMetrics {
  epoch: number;
  acc: number;
  iou: number;
  dice: number;
}

interface MetricsChartProps {
  data: EpochMetrics[];
  className?: string;
}

export function MetricsChart({ data, className }: MetricsChartProps) {
  return (
    <div className={cn("w-full h-64", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis
            dataKey="epoch"
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickFormatter={(v) => `E${v}`}
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickFormatter={(v) => (v * 100).toFixed(0) + "%"}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "hsl(var(--popover))",
              border: "1px solid hsl(var(--border))",
              borderRadius: "6px",
            }}
            labelFormatter={(v) => `Epoch ${v}`}
            formatter={(v: any) => [typeof v === "number" ? (v * 100).toFixed(1) + "%" : "—", "Score"]}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="acc"
            name="Accuracy"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="iou"
            name="IoU"
            stroke="hsl(var(--success))"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="dice"
            name="Dice"
            stroke="hsl(var(--warning))"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}