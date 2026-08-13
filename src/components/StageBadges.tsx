import { Badge } from "@/components/ui/badge";
import type { RiskTier, Stage } from "@/types/job";

const STAGE_VARIANTS: Record<
  Stage,
  "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info"
> = {
  pre_masking: "info",
  awaiting_annotation: "warning",
  researching: "info",
  awaiting_approval: "destructive",
  training: "info",
  done: "success",
  rejected: "secondary",
  error: "destructive",
};

const STAGE_LABEL: Record<Stage, string> = {
  pre_masking: "Pre-masking",
  awaiting_annotation: "Awaiting annotation",
  researching: "Researching",
  awaiting_approval: "Awaiting approval",
  training: "Training",
  done: "Done",
  rejected: "Rejected",
  error: "Error",
};

export function StageBadge({ stage }: { stage: Stage }) {
  return <Badge variant={STAGE_VARIANTS[stage]}>{STAGE_LABEL[stage]}</Badge>;
}

const RISK_VARIANTS: Record<
  NonNullable<RiskTier>,
  "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info"
> = {
  low: "success",
  medium: "warning",
  high: "destructive",
  auto: "info",
};

export function RiskBadge({ tier }: { tier: RiskTier | null }) {
  if (!tier) return <Badge variant="outline">—</Badge>;
  return <Badge variant={RISK_VARIANTS[tier]}>{tier}</Badge>;
}
