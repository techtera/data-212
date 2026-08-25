'use client';

import type { Job } from '@/lib/api';
import { FlaskConical, Wrench } from 'lucide-react';
import Link from 'next/link';

const STATUS_STYLES: Record<string, string> = {
  uploading: 'bg-warning/10 text-warning',
  running: 'bg-primary/10 text-primary',
  done: 'bg-success/10 text-success',
  error: 'bg-destructive/10 text-destructive',
};

export function JobCard({ job }: { job: Job }) {
  const statusClass = STATUS_STYLES[job.status] || 'bg-muted/10 text-muted';
  const isEval = job.job_type === 'eval';

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="block border border-border/40 rounded-2xl p-4 bg-card/40 hover:bg-card/70 hover:border-border/70 transition-all group"
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2.5">
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${isEval ? 'bg-primary/10' : 'bg-warning/10'}`}>
            {isEval ? <FlaskConical size={14} className="text-primary" /> : <Wrench size={14} className="text-warning" />}
          </div>
          <span className="text-sm font-medium">{job.job_type === 'eval' ? 'Inference' : 'Fine-tune'}</span>
        </div>
        <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium ${statusClass}`}>
          {job.status}
        </span>
      </div>
      {job.name && (
        <p className="text-sm font-semibold text-foreground/90 mb-1.5 group-hover:text-foreground transition-colors">{job.name}</p>
      )}
      <div className="text-xs text-muted space-y-0.5">
        <p>{job.model_name}</p>
        <p>{new Date(job.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</p>
      </div>
    </Link>
  );
}
