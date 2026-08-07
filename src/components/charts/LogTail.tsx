"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { LogLine } from "@/types/metrics";

interface LogTailProps {
  lines: LogLine[];
  maxLines?: number;
  className?: string;
}

export function LogTail({ lines, maxLines = 200, className }: LogTailProps) {
  const displayLines = React.useMemo(
    () => lines.slice(-maxLines),
    [lines, maxLines]
  );

  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [displayLines]);

  const getLevelColor = (level: LogLine["level"]) => {
    switch (level) {
      case "error":
        return "text-rose-400";
      case "warn":
        return "text-amber-400";
      default:
        return "text-zinc-300";
    }
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "font-mono text-xs bg-zinc-950 rounded border p-3 h-64 overflow-y-auto",
        className
      )}
      role="log"
      aria-live="polite"
      aria-label="Training log"
    >
      {displayLines.length === 0 && (
        <div className="text-zinc-500 italic">No log lines yet…</div>
      )}
      {displayLines.map((line, i) => (
        <div
          key={i}
          className={cn("flex gap-2", getLevelColor(line.level))}
          style={{ whiteSpace: "pre-wrap" }}
        >
          <span className="text-zinc-500 shrink-0">
            {new Date(line.ts).toLocaleTimeString()}
          </span>
          <span className="text-zinc-400 shrink-0 capitalize">{line.level}</span>
          <span>{line.msg}</span>
        </div>
      ))}
    </div>
  );
}