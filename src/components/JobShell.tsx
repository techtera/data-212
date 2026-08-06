"use client";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { StageBanner } from "@/components/StageBanner";
import { useJobPolling } from "@/lib/polling";
import { useJobStore } from "@/store/jobStore";
import { useNavStore } from "@/store/navStore";

import { JobsTab } from "@/components/tabs/JobsTab";
import { TrainTab } from "@/components/tabs/TrainTab";
import { AnnotateTab } from "@/components/tabs/AnnotateTab";
import { DataTab } from "@/components/tabs/DataTab";
import { ComputeTab } from "@/components/tabs/ComputeTab";
import { LogsTab } from "@/components/tabs/LogsTab";
import { ResultsTab } from "@/components/tabs/ResultsTab";
import { InferenceTab } from "@/components/tabs/InferenceTab";

const TABS = [
  { value: "jobs", label: "Jobs", render: JobsTab },
  { value: "train", label: "Train", render: TrainTab },
  { value: "annotate", label: "Annotate", render: AnnotateTab },
  { value: "data", label: "Data", render: DataTab },
  { value: "compute", label: "Compute", render: ComputeTab },
  { value: "logs", label: "Logs", render: LogsTab },
  { value: "results", label: "Results", render: ResultsTab },
  { value: "inference", label: "Inference", render: InferenceTab },
] as const;

export function JobShell() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const activeTab = useNavStore((s) => s.activeTab);
  const setActiveTab = useNavStore((s) => s.setActiveTab);
  useJobPolling(activeJobId);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-4">
        <h1 className="text-3xl font-bold tracking-tight">Cloud Training UI</h1>
        <p className="text-sm text-muted-foreground">
          TERAFAC V1 — single-user, dark theme, MSW mock backend.
        </p>
      </header>

      <StageBanner />

      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as typeof activeTab)}
        className="w-full"
      >
        <TabsList className="flex flex-wrap">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {TABS.map((t) => {
          const Comp = t.render;
          return (
            <TabsContent key={t.value} value={t.value} className="mt-4">
              <Comp />
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
