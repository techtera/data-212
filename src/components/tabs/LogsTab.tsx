"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LogsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Logs</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          LossChart + MetricsChart + LogTail land in M6. Source:
          /jobs/{`{id}`}/logs.
        </p>
      </CardContent>
    </Card>
  );
}
