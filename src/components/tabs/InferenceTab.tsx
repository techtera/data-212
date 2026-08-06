"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function InferenceTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Inference</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          CodeBlock + Copy + Download inference.py + Download checkpoint
          land in M7. Source: /jobs/{`{id}`}/inference.
        </p>
      </CardContent>
    </Card>
  );
}
