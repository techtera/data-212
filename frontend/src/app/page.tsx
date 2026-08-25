'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { getJobs, type Job } from '@/lib/api';
import { Protected } from '@/components/protected';
import { Navbar } from '@/components/navbar';
import { JobCard } from '@/components/job-card';
import { Plus, Inbox } from 'lucide-react';
import Link from 'next/link';

function DashboardContent() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchJobs = useCallback(async () => {
    if (!token) return;
    try {
      const data = await getJobs(token);
      setJobs(data);
    } catch {
      // silently fail on refresh
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    const hasRunning = jobs.some((j) => j.status === 'running' || j.status === 'uploading');
    if (!hasRunning) return;
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [jobs, fetchJobs]);

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="px-8 py-10 max-w-[1400px] mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
            <p className="text-sm text-muted mt-0.5">{jobs.length} {jobs.length === 1 ? 'job' : 'jobs'}</p>
          </div>
          <Link
            href="/new-job"
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:brightness-110 transition-all shadow-sm shadow-primary/20"
          >
            <Plus size={15} />
            New Job
          </Link>
        </div>

        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin rounded-full h-7 w-7 border-2 border-primary border-t-transparent" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-24 text-muted">
            <div className="w-16 h-16 rounded-2xl bg-card/60 flex items-center justify-center mx-auto mb-4">
              <Inbox size={28} className="opacity-40" />
            </div>
            <p className="text-base font-medium">No jobs yet</p>
            <p className="text-sm mt-1 text-muted/70">Create your first inference or fine-tuning job to get started</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Protected>
      <DashboardContent />
    </Protected>
  );
}
