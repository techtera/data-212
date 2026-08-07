"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DataPreviewImage } from "@/types/job";

export function DataTab() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const [images, setImages] = useState<DataPreviewImage[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchPreview = useCallback(async () => {
    if (!activeJobId) return;
    setLoading(true);
    try {
      const data = await api.getDataPreview(activeJobId);
      setImages(data);
    } catch {
      setImages([]);
    } finally {
      setLoading(false);
    }
  }, [activeJobId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchPreview();
  }, [fetchPreview]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Data</CardTitle>
        <Button variant="outline" size="sm" onClick={fetchPreview} disabled={loading || !activeJobId}>
          {loading ? "Re-sampling…" : "Re-sample"}
        </Button>
      </CardHeader>
      <CardContent>
        {!activeJobId && (
          <p className="text-sm text-muted-foreground">
            No active job. Use the Train tab to start one.
          </p>
        )}

        {activeJobId && images.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground">No preview images available.</p>
        )}

        {loading && <p className="text-sm text-muted-foreground">Loading preview…</p>}

        {images.length > 0 && (
          <div
            className={cn(
              "grid gap-2",
              "grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8"
            )}
            role="list"
            aria-label="Dataset preview"
          >
            {images.map((img) => (
              <figure key={img.image_id} className="relative aspect-square rounded border overflow-hidden bg-zinc-900">
                <img
                  src={img.url}
                  alt={`Preview ${img.image_id}`}
                  className="w-full h-full object-cover transition-opacity duration-200 hover:opacity-80"
                  loading="lazy"
                />
                <figcaption className="absolute bottom-0 left-0 right-0 px-1 py-0.5 bg-black/60 text-[10px] text-white truncate">
                  {img.image_id}
                </figcaption>
              </figure>
            ))}
          </div>
        )}

        {images.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            Showing {images.length} random images from the dataset. Masks are not shown here (surfaced in Annotate & Results).
          </p>
        )}
      </CardContent>
    </Card>
  );
}