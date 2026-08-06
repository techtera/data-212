import { create } from "zustand";

export type TabValue =
  | "jobs"
  | "train"
  | "annotate"
  | "data"
  | "compute"
  | "logs"
  | "results"
  | "inference";

interface NavState {
  activeTab: TabValue;
  setActiveTab: (t: TabValue) => void;
}

export const useNavStore = create<NavState>((set) => ({
  activeTab: "jobs",
  setActiveTab: (t) => set({ activeTab: t }),
}));
