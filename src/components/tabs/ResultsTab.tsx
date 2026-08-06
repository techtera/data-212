"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ResultsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Results</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Final metrics + sample predictions + risk banner land in M6.
          Source: /jobs/{`{id}`}/results.
        </p>
      </CardContent>
    </Card>
  );
}
