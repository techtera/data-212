"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ComputeTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Compute</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Live VRAM / GPU gauges land in M5. Polls /jobs/{`{id}`}/compute every
          3 s only while this tab is open.
        </p>
      </CardContent>
    </Card>
  );
}
