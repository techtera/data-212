"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useJobStore } from "@/store/jobStore";
import { api } from "@/lib/api";
import type { FlaggedImage } from "@/types/job";

type ImageItem = { src: string; id: string };

interface PolygonPoint {
  x: number;
  y: number;
}

interface AnnotationState {
  polygons: PolygonPoint[][];
  currentPolygon: PolygonPoint[];
}

export function AnnotatorWrapper() {
  const jobId = useJobStore((s) => s.activeJobId);
  const flagged = useJobStore((s) => s.job?.flagged ?? []) as FlaggedImage[];
  const resetAnnotations = useJobStore((s) => s.resetAnnotations);

  const [images, setImages] = useState<ImageItem[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [savedCount, setSavedCount] = useState(0);
  const [lastSavedIdx, setLastSavedIdx] = useState<number | null>(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [training, setTraining] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const previewCanvasRef = useRef<HTMLCanvasElement>(null);

  // Click handling: use timeout to distinguish click vs double-click
  const clickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const total = flagged.length;

  // Per-image saved tracking (from temp folder)
  const [savedImages, setSavedImages] = useState<Set<string>>(new Set());

  // Saved polygons per image for preview
  const [savedPolygonsMap, setSavedPolygonsMap] = useState<Record<string, PolygonPoint[][]>>({});

  const [annotationState, setAnnotationState] = useState<AnnotationState>({
    polygons: [],
    currentPolygon: [],
  });

  // Confirm dialog state for reset
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  // Fetch saved count from temp folder
  const fetchSavedCount = useCallback(async () => {
    if (!jobId) return;
    try {
      const res = await fetch(`/api/save-mask?jobId=${jobId}`);
      if (res.ok) {
        const data = await res.json();
        setSavedCount(data.savedCount || 0);
        if (data.savedImages) {
          setSavedImages(new Set(data.savedImages));
        }
      }
    } catch {
      setSavedCount(0);
      setSavedImages(new Set());
    }
  }, [jobId]);

  useEffect(() => {
    queueMicrotask(() => fetchSavedCount());
    const interval = setInterval(fetchSavedCount, 2000);
    return () => clearInterval(interval);
  }, [fetchSavedCount]);

  // drawCanvas
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const maxWidth = canvas.parentElement?.clientWidth ?? 800;
    const scale = Math.min(1, maxWidth / img.width);
    const displayWidth = img.width * scale;
    const displayHeight = img.height * scale;

    canvas.width = displayWidth * dpr;
    canvas.height = displayHeight * dpr;
    canvas.style.width = `${displayWidth}px`;
    canvas.style.height = `${displayHeight}px`;

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, displayWidth, displayHeight);
    ctx.drawImage(img, 0, 0, displayWidth, displayHeight);

    // Draw completed polygons
    ctx.strokeStyle = "#22c55e";
    ctx.lineWidth = 2;
    ctx.fillStyle = "rgba(34, 197, 94, 0.15)";

    for (const poly of annotationState.polygons) {
      if (poly.length < 2) continue;
      ctx.beginPath();
      ctx.moveTo(poly[0].x, poly[0].y);
      for (let i = 1; i < poly.length; i++) {
        ctx.lineTo(poly[i].x, poly[i].y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    // Draw current polygon being drawn
    if (annotationState.currentPolygon.length > 0) {
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(annotationState.currentPolygon[0].x, annotationState.currentPolygon[0].y);
      for (let i = 1; i < annotationState.currentPolygon.length; i++) {
        ctx.lineTo(annotationState.currentPolygon[i].x, annotationState.currentPolygon[i].y);
      }
      if (annotationState.currentPolygon.length > 2) {
        ctx.closePath();
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw vertices
      ctx.fillStyle = "#f59e0b";
      for (const pt of annotationState.currentPolygon) {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Draw vertices for completed polygons
    ctx.fillStyle = "#22c55e";
    for (const poly of annotationState.polygons) {
      for (const pt of poly) {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }, [annotationState]);

  // Draw saved annotation on preview canvas (side-by-side view)
  const drawPreviewCanvas = useCallback(() => {
    const canvas = previewCanvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const maxWidth = canvas.parentElement?.clientWidth ?? 400;
    const scale = Math.min(1, maxWidth / img.width);
    const displayWidth = img.width * scale;
    const displayHeight = img.height * scale;

    canvas.width = displayWidth * dpr;
    canvas.height = displayHeight * dpr;
    canvas.style.width = `${displayWidth}px`;
    canvas.style.height = `${displayHeight}px`;

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, displayWidth, displayHeight);
    ctx.drawImage(img, 0, 0, displayWidth, displayHeight);

    // Use saved polygons for current image if available, else current annotationState
    const currentImage = images[selectedIdx];
    const savedPolys = currentImage ? savedPolygonsMap[currentImage.id] : null;
    const polysToDraw = savedPolys && savedPolys.length > 0 ? savedPolys : annotationState.polygons;

    if (polysToDraw.length > 0) {
      ctx.strokeStyle = "#22c55e";
      ctx.lineWidth = 2;
      ctx.fillStyle = "rgba(34, 197, 94, 0.15)";

      for (const poly of polysToDraw) {
        if (poly.length < 2) continue;
        ctx.beginPath();
        ctx.moveTo(poly[0].x * (displayWidth / (img.width || 1)), poly[0].y * (displayHeight / (img.height || 1)));
        for (let i = 1; i < poly.length; i++) {
          ctx.lineTo(poly[i].x * (displayWidth / (img.width || 1)), poly[i].y * (displayHeight / (img.height || 1)));
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }
  }, [annotationState, images, selectedIdx, savedPolygonsMap]);

  // Keyboard handler
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape" && annotationState.currentPolygon.length > 0) {
      setAnnotationState((prev) => ({ ...prev, currentPolygon: [] }));
    }
    if (e.key === "Backspace" && annotationState.currentPolygon.length > 0) {
      setAnnotationState((prev) => ({
        ...prev,
        currentPolygon: prev.currentPolygon.slice(0, -1),
      }));
    }
    if (e.key === "Delete" && annotationState.polygons.length > 0) {
      setAnnotationState((prev) => ({
        ...prev,
        polygons: prev.polygons.slice(0, -1),
      }));
    }
  }, [annotationState]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    if (flagged.length > 0) {
      queueMicrotask(() => {
        setImages(
          flagged.map((f, i) => ({
            src: f.url,
            id: f.image_id,
          }))
        );
      });
    }
  }, [flagged]);

  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = images[selectedIdx]?.src ?? "";
    img.onload = () => {
      imgRef.current = img;
      setImageLoaded(true);
      drawCanvas();
      drawPreviewCanvas();
    };
    img.onerror = () => {
      toast.error("Failed to load image");
      setImageLoaded(true);
    };
  }, [images, selectedIdx, drawCanvas, drawPreviewCanvas]);

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!imageLoaded) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Delay to allow double-click to cancel this
    if (clickTimeoutRef.current) clearTimeout(clickTimeoutRef.current);
    clickTimeoutRef.current = setTimeout(() => {
      setAnnotationState((prev) => ({
        ...prev,
        currentPolygon: [...prev.currentPolygon, { x, y }],
      }));
    }, 200);
  }, [imageLoaded]);

  const handleCanvasDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (clickTimeoutRef.current) {
      clearTimeout(clickTimeoutRef.current);
      clickTimeoutRef.current = null;
    }

    if (annotationState.currentPolygon.length < 3) return;

    // Close the polygon by adding the first point as the last point
    const closedPolygon = [
      ...annotationState.currentPolygon,
      annotationState.currentPolygon[0]
    ];

    setAnnotationState((prev) => ({
      ...prev,
      polygons: [...prev.polygons, closedPolygon],
      currentPolygon: [],
    }));
  }, [annotationState]);

  // Save current polygon for current image to temp folder
  const handleSaveMask = useCallback(async () => {
    // Allow saving if there's a current polygon being drawn (>=3 points) or completed polygons
    if (!jobId || (annotationState.currentPolygon.length < 3 && annotationState.polygons.length === 0)) {
      toast.error("Draw at least 3 points to create a polygon");
      return;
    }

    setSaving(true);
    try {
      const imageId = images[selectedIdx]?.id;
      if (!imageId) {
        toast.error("No image selected");
        return;
      }

      // Prepare polygons: include completed ones + the current one if it has >=3 points
      const allPolygons = [...annotationState.polygons];
      if (annotationState.currentPolygon.length >= 3) {
        // Close the current polygon
        const closedPolygon = [
          ...annotationState.currentPolygon,
          annotationState.currentPolygon[0]
        ];
        allPolygons.push(closedPolygon);
      }

      if (allPolygons.length === 0) {
        toast.error("No polygons to save");
        return;
      }

      // Send polygons to API
      const polygons = allPolygons.map((p) => p.map((pt) => [pt.x, pt.y]));
      
      const res = await fetch("/api/save-mask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobId, imageId, polygons }),
      });

      if (!res.ok) throw new Error("Failed to save");

      const isNewSave = !savedImages.has(imageId);
      toast.success(isNewSave ? `Saved mask for image ${imageId}` : `Updated mask for image ${imageId}`);
      setLastSavedIdx(selectedIdx);
      
      // Store polygons for preview
      setSavedPolygonsMap(prev => ({ ...prev, [imageId]: allPolygons }));
      
      // Optimistically update savedImages
      if (isNewSave) {
        setSavedImages(prev => new Set(prev).add(imageId));
        setSavedCount(prev => prev + 1);
      }
      
      // Clear polygons for this image so user can draw for next image
      setAnnotationState({ polygons: [], currentPolygon: [] });
      
    } catch (err) {
      toast.error(`Failed to save mask: ${String(err)}`);
    } finally {
      setSaving(false);
    }
  }, [jobId, images, selectedIdx, annotationState.polygons, annotationState.currentPolygon, savedImages]);

  // Start training - call POST /jobs/{id}/annotations
  const handleStartTraining = useCallback(async () => {
    if (!jobId) return;
    if (savedCount < total) {
      toast.error(`Save all ${total} masks first (${savedCount}/${total} done)`);
      return;
    }

    setTraining(true);
    try {
      await api.sendAnnotations(jobId, new Blob(["temp"], { type: "application/zip" }));
      toast.success("Training started!");
      resetAnnotations();
    } catch (err) {
      toast.error(`Failed to start training: ${String(err)}`);
    } finally {
      setTraining(false);
    }
  }, [jobId, savedCount, total, resetAnnotations]);

  const handleNext = useCallback(() => {
    if (selectedIdx < flagged.length - 1) setSelectedIdx((i) => i + 1);
  }, [selectedIdx, flagged.length]);

  const handlePrev = useCallback(() => {
    if (selectedIdx > 0) setSelectedIdx((i) => i - 1);
  }, [selectedIdx]);

  // Reset all annotations (with confirmation)
  const handleReset = useCallback(() => {
    setShowResetConfirm(true);
  }, []);

  const handleResetConfirm = useCallback(async () => {
    if (!jobId) {
      setShowResetConfirm(false);
      return;
    }

    try {
      // Delete ALL mask files from disk (no imageId param) so the next poll
      // doesn't resurrect them
      const res = await fetch(`/api/save-mask?jobId=${jobId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete mask files");
    } catch (err) {
      toast.error(`Failed to delete masks: ${String(err)}`);
      // still clear local state and close dialog
    }

    // Clear the entire saved polygons map
    setSavedPolygonsMap({});
    // Clear all saved images and reset count to 0
    setSavedImages(new Set());
    setSavedCount(0);
    // Clear local annotation state for the currently selected image
    setAnnotationState({ polygons: [], currentPolygon: [] });
    setShowResetConfirm(false);
    toast.success("All annotations reset");
  }, [jobId]);

  const handleResetCancel = useCallback(() => {
    setShowResetConfirm(false);
  }, []);

  if (!jobId || images.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Annotate</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No active job or no flagged images. Complete the Train tab flow
            first.
          </p>
        </CardContent>
      </Card>
    );
  }

  const currentImage = images[selectedIdx];
  const isCurrentImageSaved = currentImage && savedImages.has(currentImage.id);

  return (
    <Card className="flex flex-col h-[calc(100vh-240px)]">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Annotate low-confidence masks</CardTitle>
        </div>
        <div className="flex items-center gap-2">
          <Progress value={total > 0 ? Math.round((savedCount / total) * 100) : 0} className="w-40" />
          <span className="text-xs font-mono text-muted-foreground">
            {savedCount}/{total}
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center gap-3 mb-3">
          <Select value={String(selectedIdx)} onValueChange={(v) => setSelectedIdx(Number(v))}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {images.map((_, i) => (
                <SelectItem key={i} value={String(i)}>
                  Image {images[i].id} {savedImages.has(images[i].id) && "✓"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handlePrev} disabled={selectedIdx === 0}>
              Prev
            </Button>
            <Button variant="outline" size="sm" onClick={handleNext} disabled={selectedIdx === total - 1}>
              Next
            </Button>
          </div>
          <span className="text-xs text-muted-foreground ml-auto">
            Click to add points, Double-click to close polygon. Click <strong>Save Mask</strong> when done.
          </span>
        </div>

        <div className="flex-1 min-h-0 flex gap-2">
          {/* Main annotation canvas */}
          <div className="flex-1 min-w-0 border rounded bg-zinc-950 relative" style={{ overflow: "hidden" }}>
            <canvas
              ref={canvasRef}
              onClick={handleCanvasClick}
              onDoubleClick={handleCanvasDoubleClick}
              style={{ display: "block", maxWidth: "100%", maxHeight: "100%", cursor: "crosshair" }}
            />
            {!imageLoaded && (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                Loading image...
              </div>
            )}
          </div>

          {/* Preview canvas showing saved mask */}
          <div className="w-1/3 min-w-0 border rounded bg-zinc-950 relative" style={{ overflow: "hidden" }}>
            <canvas
              ref={previewCanvasRef}
              style={{ display: "block", maxWidth: "100%", maxHeight: "100%" }}
            />
            {!imageLoaded && (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-xs">
                Preview
              </div>
            )}
          </div>
        </div>

        <div className="mt-3 flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => setAnnotationState((p) => ({ ...p, currentPolygon: [] }))} disabled={annotationState.currentPolygon.length === 0}>
            Clear Current Polygon
          </Button>
          <Button variant="outline" size="sm" onClick={handleReset} disabled={annotationState.polygons.length === 0 && annotationState.currentPolygon.length === 0 && !isCurrentImageSaved}>
            Reset
          </Button>
          <Button onClick={handleSaveMask} disabled={saving || (annotationState.polygons.length === 0 && annotationState.currentPolygon.length < 3)}>
            {saving ? "Saving..." : "Save Mask"}
          </Button>

          {/* Reset Confirmation Dialog */}
          {showResetConfirm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
              <div className="fixed inset-0 bg-black/50" onClick={handleResetCancel} aria-hidden="true" />
              <div className="relative z-50 w-full max-w-md rounded-lg bg-popover p-6 shadow-lg border">
                <h3 className="text-lg font-semibold mb-2">Reset Annotations?</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  This will clear all saved and current annotations for this image. This action cannot be undone.
                </p>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={handleResetCancel}>
                    No
                  </Button>
                  <Button variant="destructive" size="sm" onClick={handleResetConfirm}>
                    Yes
                  </Button>
                </div>
              </div>
            </div>
          )}
          {savedCount === total && (
            <Button onClick={handleStartTraining} disabled={training} className="bg-emerald-600 hover:bg-emerald-700">
              {training ? "Starting..." : "Start Training"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}