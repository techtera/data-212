"use client";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const TABS = [
  { value: "jobs", label: "Jobs", milestone: "M3" },
  { value: "train", label: "Train", milestone: "M3" },
  { value: "annotate", label: "Annotate", milestone: "M4" },
  { value: "data", label: "Data", milestone: "M5" },
  { value: "compute", label: "Compute", milestone: "M5" },
  { value: "logs", label: "Logs", milestone: "M6" },
  { value: "results", label: "Results", milestone: "M6" },
  { value: "inference", label: "Inference", milestone: "M7" },
] as const;

export function JobShell() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Cloud Training UI</h1>
        <p className="text-sm text-muted-foreground">
          TERAFAC V1 — single-user, dark theme, MSW mock backend.
        </p>
      </header>

      <Tabs defaultValue="jobs" className="w-full">
        <TabsList className="flex flex-wrap">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {TABS.map((t) => (
          <TabsContent key={t.value} value={t.value} className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>{t.label}</CardTitle>
                <CardDescription>
                  Lands in milestone {t.milestone}.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Placeholder. Real content for this tab is wired in milestone{" "}
                  {t.milestone}.
                </p>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
