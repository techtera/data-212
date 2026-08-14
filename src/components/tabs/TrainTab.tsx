"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { UploadProgress } from "@/components/UploadProgress";
import { useJobStore } from "@/store/jobStore";
import { useNavStore } from "@/store/navStore";

export function TrainTab() {
  const prompt = useJobStore((s) => s.prompt);
  const setPrompt = useJobStore((s) => s.setPrompt);

  const uploadedFileName = useJobStore((s) => s.uploadedFileName);
  const uploadProgress = useJobStore((s) => s.uploadProgress);
  const isUploading = useJobStore((s) => s.isUploading);
  const setUploadProgress = useJobStore((s) => s.setUploadProgress);
  const setIsUploading = useJobStore((s) => s.setIsUploading);
  const setUploadedFileName = useJobStore((s) => s.setUploadedFileName);
  const setDatasetPath = useJobStore((s) => s.setDatasetPath);
  const setActiveJobId = useJobStore((s) => s.setActiveJobId);

  const job = useJobStore((s) => s.job);
  const blocked =
    Boolean(job) && job?.stage === "awaiting_annotation" &&
    (job?.unannotated_count ?? 0) > 0;

  const setActiveTab = useNavStore((s) => s.setActiveTab);

  const [submitting, setSubmitting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const uploadTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const uploadDone = !isUploading && (uploadProgress ?? 0) >= 100 && Boolean(uploadedFileName);
  const promptValid = prompt.trim().length > 0;
  const fileValid = Boolean(uploadedFileName);
  const canStart =
    promptValid && fileValid && !blocked && !submitting;

  function startFakeUpload(file: File) {
    if (uploadTimer.current) clearInterval(uploadTimer.current);
    setSelectedFile(file);
    setUploadedFileName(file.name);
    setUploadProgress(0);
    setIsUploading(false);
  }

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Please select a .zip file (raw images, no masks).");
      e.target.value = "";
      return;
    }
    startFakeUpload(file);
  }

  async function onStart() {
    if (!canStart || !selectedFile) return;
    setSubmitting(true);
    setIsUploading(true);
    setUploadProgress(10);
    try {
      // Two-hop upload: sign → PUT directly to GCS (no auth header on PUT)
      setUploadProgress(30);
      const uploadResult = await api.uploadDataset(selectedFile);
      setUploadProgress(80);
      setDatasetPath(uploadResult.object_path);

      // Create the job with the object_path from the signed upload
      const created = await api.createJob({
        prompt: prompt.trim(),
        dataset_object_path: uploadResult.object_path,
      });
      setUploadProgress(100);
      setIsUploading(false);

      setActiveJobId(created.job_id);
      toast.success(`Job ${created.job_id} created — stage: ${created.stage}`);
      setActiveTab("annotate");
    } catch (err) {
      toast.error(`Failed to start job: ${String(err)}`);
      setIsUploading(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Train</CardTitle>
        <CardDescription>
          Pick a .zip of raw images (no masks) and describe what you want to
          train. The backend decides the rest from your prompt.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <label
            htmlFor="train-prompt"
            className="text-sm font-medium leading-none"
          >
            Prompt <span className="text-rose-400">*</span>
          </label>
          <Textarea
            id="train-prompt"
            placeholder="e.g. train a model to segment rooftops in aerial photos"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            disabled={submitting}
          />
          {!promptValid && (
            <p className="text-xs text-muted-foreground">
              A prompt is required.
            </p>
          )}
        </div>

        <div className="space-y-2">
          <label
            htmlFor="train-dataset"
            className="text-sm font-medium leading-none"
          >
            Dataset <span className="text-rose-400">*</span>
          </label>
          <Input
            id="train-dataset"
            type="file"
            accept=".zip"
            onChange={onPickFile}
            disabled={submitting}
          />
          <p className="text-xs text-muted-foreground">
            Accepts <code className="font-mono">.zip</code> of raw images.
            Masks are produced by the pretrained checkpoint, not included.
          </p>
        </div>

        <UploadProgress
          fileName={uploadedFileName}
          progress={uploadProgress}
          isUploading={isUploading}
        />

        {blocked && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            The active job is waiting on annotation of low-confidence masks.
            Training will start once all images are re-annotated.
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button
            onClick={onStart}
            disabled={!canStart}
            data-testid="start-job"
          >
            {submitting ? "Starting..." : "Start job"}
          </Button>
          {!uploadDone && fileValid && (
            <span className="text-xs text-muted-foreground">
              Uploading in progress — Start will enable once it finishes.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
