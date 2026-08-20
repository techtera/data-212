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

  // Auto-refresh every 5 seconds if there are running jobs
  useEffect(() => {
    const hasRunning = jobs.some((j) => j.status === 'running' || j.status === 'uploading');
    if (!hasRunning) return;

    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [jobs, fetchJobs]);

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold">Your Jobs</h1>
          <Link
            href="/new-job"
            className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity text-sm"
          >
            <Plus size={16} />
            New Job
          </Link>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-16 text-muted">
            <Inbox size={48} className="mx-auto mb-4 opacity-50" />
            <p className="text-lg">No jobs yet</p>
            <p className="text-sm mt-1">Create your first evaluation or fine-tuning job</p>
          </div>
        ) : (
          <div className="grid gap-3">
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
