import { create } from "zustand";

import type { Stage, RiskTier, JobProgress } from "@/types/job";

export interface CocoEntry {
  image_id: string;
  segmentation: number[][];
  saved_at: string;
  category_id: number;
  bbox: [number, number, number, number];
  area: number;
  is_crowd: number;
}

export interface JobStoreState {
  activeJobId: string | null;
  prompt: string;
  datasetObjectPath: string | null;
  uploadProgress: number;
  isUploading: boolean;
  uploadedFileName: string | null;
  job: JobProgress | null;
  riskTier: RiskTier | null;
  cocoMap: Record<string, CocoEntry>;

  setPrompt: (p: string) => void;
  setDatasetPath: (p: string | null) => void;
  setUploadProgress: (n: number) => void;
  setIsUploading: (b: boolean) => void;
  setUploadedFileName: (f: string | null) => void;
  setActiveJobId: (id: string | null) => void;
  setJob: (j: JobProgress | null) => void;
  setRiskTier: (r: RiskTier | null) => void;
  saveCoco: (entry: CocoEntry) => void;
  resetAnnotations: () => void;
  resetAll: () => void;
}

const EMPTY = {
  activeJobId: null,
  prompt: "",
  datasetObjectPath: null,
  uploadProgress: 0,
  isUploading: false,
  uploadedFileName: null,
  job: null,
  riskTier: null,
  cocoMap: {},
} as const;

export const useJobStore = create<JobStoreState>((set) => ({
  ...EMPTY,

  setPrompt: (p) => set({ prompt: p }),
  setDatasetPath: (p) => set({ datasetObjectPath: p }),
  setUploadProgress: (n) => set({ uploadProgress: n }),
  setIsUploading: (b) => set({ isUploading: b }),
  setUploadedFileName: (f) => set({ uploadedFileName: f }),

  setActiveJobId: (id) => set({ activeJobId: id }),
  setJob: (j) => set({ job: j }),
  setRiskTier: (r) => set({ riskTier: r }),

  saveCoco: (entry) =>
    set((s) => ({
      cocoMap: { ...s.cocoMap, [entry.image_id]: entry },
    })),

  resetAnnotations: () => set({ cocoMap: {} }),
  resetAll: () => set({ ...EMPTY }),
}));

export type { Stage };
