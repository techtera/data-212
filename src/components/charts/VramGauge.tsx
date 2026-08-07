"use client";

import * as React from "react";
import { RadialBarChart, RadialBar, Cell } from "recharts";
import { cn } from "@/lib/utils";

interface VramGaugeProps {
  usedMb: number;
  totalMb: number;
  className?: string;
}

export function VramGauge({ usedMb, totalMb, className }: VramGaugeProps) {
  const pct = totalMb > 0 ? Math.round((usedMb / totalMb) * 100) : 0;
  const data = [
    { name: "VRAM", value: pct },
    { name: "Remaining", value: 100 - pct },
  ];

  const getColor = (p: number) => {
    if (p >= 90) return "hsl(var(--destructive))";
    if (p >= 70) return "hsl(var(--warning))";
    return "hsl(var(--primary))";
  };

  const RADIUS = 80;

  return (
    <div className={cn("relative w-48 h-48 flex items-center justify-center", className)}>
      <RadialBarChart width={RADIUS * 2} height={RADIUS * 2} data={data} cx={RADIUS} cy={RADIUS} innerRadius={RADIUS * 0.7} outerRadius={RADIUS * 0.9}>
        <RadialBar
          dataKey="value"
          background={{ fill: "hsl(var(--border))" }}
        >
          <Cell fill="hsl(var(--border))" />
        </RadialBar>
        <RadialBar
          dataKey="value"
          fill={getColor(pct)}
        >
          <Cell fill={getColor(pct)} />
        </RadialBar>
      </RadialBarChart>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold tabular-nums">{pct}%</span>
        <span className="text-xs text-muted-foreground">
          {usedMb.toLocaleString()} / {totalMb.toLocaleString()} MB
        </span>
      </div>
    </div>
  );
}