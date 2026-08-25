'use client';

import type { Job } from '@/lib/api';
import { FlaskConical, Wrench } from 'lucide-react';
import Link from 'next/link';

const STATUS_STYLES: Record<string, string> = {
  uploading: 'bg-warning/15 text-warning border-warning/20',
  running: 'bg-primary/15 text-primary border-primary/20',
  done: 'bg-success/15 text-success border-success/20',
  error: 'bg-destructive/15 text-destructive border-destructive/20',
};

export function JobCard({ job }: { job: Job }) {
  const statusClass = STATUS_STYLES[job.status] || 'bg-muted/10 text-muted';
  const isEval = job.job_type === 'eval';

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="block border border-border/50 rounded-2xl p-5 bg-card/60 hover:bg-card hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 transition-all duration-200 group"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${isEval ? 'bg-gradient-to-br from-primary/20 to-primary/5' : 'bg-gradient-to-br from-warning/20 to-warning/5'}`}>
            {isEval ? <FlaskConical size={15} className="text-primary" /> : <Wrench size={15} className="text-warning" />}
          </div>
          <span className="text-sm font-semibold text-foreground/90">{job.job_type === 'eval' ? 'Inference' : 'Fine-tune'}</span>
        </div>
        <span className={`text-[11px] px-2.5 py-1 rounded-lg font-semibold border ${statusClass}`}>
          {job.status}
        </span>
      </div>
      {job.name && (
        <p className="text-base font-semibold text-foreground group-hover:text-primary transition-colors mb-1">{job.name}</p>
      )}
      <div className="text-sm text-muted space-y-0.5">
        <p>{job.model_name}</p>
        <p className="text-xs">{new Date(job.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} at {new Date(job.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</p>
      </div>
    </Link>
  );
}
