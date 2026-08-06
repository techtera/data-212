"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";

interface UseJobPollingOptions {
  intervalMs?: number;
  enabled?: boolean;
}

export function useJobPolling(
  jobId: string | null,
  opts: UseJobPollingOptions = {}
) {
  const intervalMs = opts.intervalMs ?? 3000;
  const enabled = opts.enabled ?? true;

  const setJob = useJobStore((s) => s.setJob);
  const setRiskTier = useJobStore((s) => s.setRiskTier);

  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const attemptsRef = useRef(0);
  const backoffRef = useRef(intervalMs);

  useEffect(() => {
    if (!jobId || !enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (cancelled) return;
      setIsPolling(true);
      try {
        const next = await api.getJob(jobId);
        if (cancelled) return;
        setJob(next);
        attemptsRef.current = 0;
        backoffRef.current = intervalMs;
        if (next.stage === "awaiting_approval" && useJobStore.getState().riskTier === null) {
          setRiskTier("medium");
        }
        setError(null);
      } catch (err) {
        attemptsRef.current += 1;
        backoffRef.current = Math.min(
          backoffRef.current * 1.5,
          15000
        );
        if (!cancelled) setError(String(err));
      } finally {
        setIsPolling(false);
        if (!cancelled) {
          timer = setTimeout(tick, backoffRef.current);
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, enabled, intervalMs, setJob, setRiskTier]);

  return { isPolling, error };
}
