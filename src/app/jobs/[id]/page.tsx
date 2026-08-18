'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Protected } from '@/components/protected';
import { Navbar } from '@/components/navbar';
import { getJobs, getResults, getDownload, type Job } from '@/lib/api';
import { toast } from 'sonner';
import { ArrowLeft, Download, Loader2, CheckCircle2, XCircle, Clock, Image as ImageIcon } from 'lucide-react';
import Link from 'next/link';


const PIPELINE_STEPS = [
  'Uploading images to cloud storage',
  'Starting inference on GPU server',
  'Downloading model to GPU server',
  'Running YOLO inference on images',
  'Uploading predictions to cloud storage',
  'Saving results',
];

function JobDetailContent() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [job, setJob] = useState<Job | null>(null);
  const [results, setResults] = useState<{ prediction_urls?: string[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [pollCount, setPollCount] = useState(0);

  const fetchJob = useCallback(async () => {
    if (!token || !id) return;
    try {
      const jobs = await getJobs(token);
      const found = jobs.find((j) => j.id === id);
      if (found) {
        setJob(found);
        if (found.status === 'done' && !results) {
          try {
            const r = await getResults(token, id);
            setResults(r);
          } catch {
            // ignore
          }
        }
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, id, results]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

  useEffect(() => {
    if (!job || (job.status !== 'running' && job.status !== 'uploading')) return;
    const interval = setInterval(() => {
      fetchJob();
      setPollCount((c) => c + 1);
    }, 3000);
    return () => clearInterval(interval);
  }, [job, fetchJob]);

  const handleDownload = async (type: 'checkpoint' | 'script') => {
    if (!token || !id) return;
    try {
      const data = await getDownload(token, id);
      const url = type === 'checkpoint' ? data.checkpoint_url : data.inference_script_url;
      if (url) window.open(url, '_blank');
      else toast.error('Download URL not available');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Download failed');
    }
  };

  const currentStep = Math.min(Math.floor(pollCount / 3), PIPELINE_STEPS.length - 1);

  const StatusBadge = ({ status }: { status: string }) => {
    const config: Record<string, { icon: React.ReactNode; text: string; className: string }> = {
      uploading: { icon: <Clock size={14} />, text: 'Preparing...', className: 'bg-warning/20 text-warning' },
      running: { icon: <Loader2 size={14} className="animate-spin" />, text: 'Running inference...', className: 'bg-primary/20 text-primary' },
      done: { icon: <CheckCircle2 size={14} />, text: 'Completed', className: 'bg-success/20 text-success' },
      error: { icon: <XCircle size={14} />, text: 'Error', className: 'bg-destructive/20 text-destructive' },
    };
    const c = config[status] || config.error;
    return (
      <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ${c.className}`}>
        {c.icon}
        {c.text}
      </span>
    );
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="max-w-2xl mx-auto px-4 py-8">
        <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted hover:text-foreground mb-6 transition-colors">
          <ArrowLeft size={14} />
          Back to Dashboard
        </Link>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
          </div>
        ) : !job ? (
          <div className="text-center py-12 text-muted">
            <p>Job not found</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-xl font-semibold">
                  {job.name || `${job.job_type === 'eval' ? 'Inference' : 'Fine-tuning'} Job`}
                </h1>
                <p className="text-sm text-muted mt-1">
                  {job.job_type === 'eval' ? 'Inference' : 'Fine-tuning'} &middot; {job.model_name}
                </p>
                <p className="text-sm text-muted">
                  Created: {new Date(job.created_at).toLocaleString()}
                </p>
              </div>
              <StatusBadge status={job.status} />
            </div>

            {/* Running state — pipeline steps */}
            {(job.status === 'running' || job.status === 'uploading') && (
              <div className="border border-border rounded-lg p-5 bg-card">
                <div className="flex items-center gap-2 mb-4">
                  <Loader2 size={18} className="text-primary animate-spin" />
                  <p className="text-foreground font-medium">Processing pipeline</p>
                </div>
                <div className="space-y-2">
                  {PIPELINE_STEPS.map((step, i) => {
                    const isDone = i < currentStep;
                    const isCurrent = i === currentStep;
                    return (
                      <div key={i} className="flex items-center gap-2.5 text-sm">
                        {isDone ? (
                          <CheckCircle2 size={14} className="text-success shrink-0" />
                        ) : isCurrent ? (
                          <Loader2 size={14} className="text-primary animate-spin shrink-0" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-border shrink-0" />
                        )}
                        <span className={isDone ? 'text-muted line-through' : isCurrent ? 'text-foreground font-medium' : 'text-muted'}>
                          {step}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-muted mt-4">
                  Running on 2x A100 80GB GPU server. Polling every 3s...
                </p>
              </div>
            )}

            {/* Error state */}
            {job.status === 'error' && (
              <div className="border border-destructive/30 rounded-lg p-4 bg-destructive/10">
                <p className="text-destructive font-medium">Job failed</p>
                <p className="text-sm text-destructive/80 mt-1">
                  {job.error_message || 'An unexpected error occurred. Please try again.'}
                </p>
              </div>
            )}

            {/* Inference results */}
            {job.status === 'done' && job.job_type === 'eval' && (
              <div className="space-y-5">
                <h2 className="text-lg font-medium">Inference Complete</h2>

                {/* Prediction images */}
                {results?.prediction_urls && results.prediction_urls.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <ImageIcon size={16} className="text-primary" />
                      <h3 className="text-sm font-medium">Prediction Images ({results.prediction_urls.length})</h3>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {results.prediction_urls.slice(0, 10).map((url, i) => (
                        <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="block border border-border rounded-md overflow-hidden hover:border-primary/50 transition-colors">
                          <img src={url} alt={`Prediction ${i + 1}`} className="w-full h-40 object-cover" loading="lazy" />
                        </a>
                      ))}
                    </div>
                    {results.prediction_urls.length > 10 && (
                      <p className="text-xs text-muted mt-2">Showing 10 of {results.prediction_urls.length} predictions</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Finetune results */}
            {job.status === 'done' && job.job_type === 'finetune' && (
              <div className="space-y-4">
                <h2 className="text-lg font-medium">Fine-tuning Complete</h2>
                <p className="text-sm text-muted">
                  Your model has been fine-tuned. Download the checkpoint and inference script below.
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={() => handleDownload('checkpoint')}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity cursor-pointer"
                  >
                    <Download size={16} />
                    Download Checkpoint
                  </button>
                  <button
                    onClick={() => handleDownload('script')}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-md border border-border text-foreground font-medium hover:bg-card transition-colors cursor-pointer"
                  >
                    <Download size={16} />
                    Inference Script
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}


export default function JobDetailPage() {
  return (
    <Protected>
      <JobDetailContent />
    </Protected>
  );
}
