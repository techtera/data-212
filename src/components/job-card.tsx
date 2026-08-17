'use client';

import type { Job } from '@/lib/api';
import { FlaskConical, Wrench } from 'lucide-react';
import Link from 'next/link';

const STATUS_STYLES: Record<string, string> = {
  uploading: 'bg-warning/20 text-warning',
  running: 'bg-primary/20 text-primary',
  done: 'bg-success/20 text-success',
  error: 'bg-destructive/20 text-destructive',
};

const MODEL_NAMES: Record<string, string> = {
  yolo_masking: 'YOLO11L Masking Model',
};

export function JobCard({ job }: { job: Job }) {
  const statusClass = STATUS_STYLES[job.status] || 'bg-muted/20 text-muted';
  const isEval = job.job_type === 'eval';

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="block border border-border rounded-lg p-4 bg-card hover:border-primary/50 transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isEval ? <FlaskConical size={16} className="text-primary" /> : <Wrench size={16} className="text-warning" />}
          <span className="font-medium capitalize">{job.job_type === 'eval' ? 'Inference' : 'Fine-tune'}</span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusClass}`}>
          {job.status}
        </span>
      </div>
      {job.name && (
        <p className="text-sm font-medium text-foreground/80 mb-1">{job.name}</p>
      )}
      <div className="text-sm text-muted space-y-1">
        <p>Model: {MODEL_NAMES[job.model_id] || job.model_id}</p>
        <p>Created: {new Date(job.created_at).toLocaleString()}</p>
      </div>
    </Link>
  );
}
