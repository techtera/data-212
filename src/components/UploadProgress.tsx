"use client";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface UploadProgressProps {
  fileName: string | null;
  progress: number;
  isUploading: boolean;
  className?: string;
}

export function UploadProgress({
  fileName,
  progress,
  isUploading,
  className,
}: UploadProgressProps) {
  const pct = Math.max(0, Math.min(100, Math.round(progress)));
  const done = !isUploading && pct >= 100 && Boolean(fileName);
  const label = done
    ? "Uploaded"
    : isUploading
      ? `Uploading dataset... ${pct}%`
      : fileName
        ? "Ready to start"
        : "No file selected";

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="truncate font-mono text-muted-foreground">
          {fileName ?? "—"}
        </span>
        <span
          className={cn(
            "font-medium",
            done
              ? "text-emerald-300"
              : isUploading
                ? "text-sky-300"
                : "text-muted-foreground"
          )}
        >
          {label}
        </span>
      </div>
      <Progress
        value={pct}
        className={cn(
          done && "[&>div]:bg-emerald-500",
          isUploading && "[&>div]:bg-sky-500"
        )}
      />
    </div>
  );
}
