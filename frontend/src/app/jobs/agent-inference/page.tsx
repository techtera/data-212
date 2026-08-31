'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Protected } from '@/components/protected';
import { Navbar } from '@/components/navbar';
import {
  getModels,
  signUpload,
  uploadToSignedUrl,
  generateInferenceCode,
  createEvalJob,
  runAgentInference,
  type Model,
} from '@/lib/api';
import { toast } from 'sonner';
import { ArrowLeft, FlaskConical, Upload, Rocket } from 'lucide-react';
import Link from 'next/link';

function AgentInferenceContent() {
  const { token } = useAuth();
  const router = useRouter();

  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [jobName, setJobName] = useState('');
  const [imagesFile, setImagesFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState('');
  const imagesRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    getModels(token).then((m) => {
      const agentModels = m.filter(x => x.is_agent && x.load_path);
      setModels(agentModels);
      if (agentModels.length > 0) setSelectedModel(agentModels[0].model_name);
    }).catch(() => {});
  }, [token]);

  const handleRunInference = async () => {
    if (!token || !selectedModel || !jobName.trim() || !imagesFile) return;
    setRunning(true);

    try {
      setStatus('AI is writing inference code...');
      await generateInferenceCode(token, '', selectedModel);

      setStatus('Uploading images...');
      const urls = await signUpload(token, jobName.trim());
      await uploadToSignedUrl(urls.images_upload_url, imagesFile);

      setStatus('Starting inference on GPU server...');
      const job = await createEvalJob(token, { model_name: selectedModel, name: jobName.trim() });
      await runAgentInference(token, job.id);

      toast.success('Inference started! Redirecting to job page...');
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Inference failed to start');
      setRunning(false);
      setStatus('');
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="max-w-2xl mx-auto px-8 py-10">
        <Link href="/new-job" className="inline-flex items-center gap-2 text-sm font-semibold text-primary bg-primary/10 hover:bg-primary/20 px-4 py-2 rounded-xl border border-primary/25 hover:border-primary/40 mb-8 transition-all">
          <ArrowLeft size={15} />
          Back
        </Link>

        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Inference with AI Agent</h1>
          <p className="text-sm text-foreground/50 mt-1">Run inference using your AI-trained model — agent generates the inference code</p>
        </div>

        {models.length === 0 && !running ? (
          <div className="rounded-2xl border border-border/40 bg-card/40 p-8 text-center">
            <FlaskConical size={32} className="mx-auto mb-3 text-muted" />
            <p className="text-sm text-muted mb-3">No AI-trained models with checkpoints found.</p>
            <p className="text-xs text-muted/70">Train a model first using the AI Agent, then come back here.</p>
            <Link
              href="/jobs/agent-train"
              className="mt-4 inline-block text-sm text-primary hover:underline"
            >
              Go to AI Agent Training
            </Link>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Model Selection */}
            <div className="rounded-2xl border border-border/40 bg-card/40 p-6">
              <div className="flex items-center gap-2 mb-4">
                <FlaskConical size={18} className="text-accent" />
                <h2 className="text-base font-semibold">Select AI-Trained Model</h2>
              </div>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={running}
                className="w-full px-3 py-2.5 rounded-xl bg-background/50 border border-border/50 focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent/50 text-foreground text-sm cursor-pointer transition-all"
              >
                {models.map((m) => (
                  <option key={m.model_name} value={m.model_name}>
                    {m.model_name} ({m.category === 'edge_mask' ? 'Edge' : 'Object'})
                  </option>
                ))}
              </select>
            </div>

            {/* Job Name */}
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Job Name</label>
              <input
                type="text"
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
                disabled={running}
                placeholder="e.g. weld-inspection-batch1"
                className="w-full px-3.5 py-2.5 rounded-xl bg-card/60 border border-border/50 focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent/50 text-foreground text-sm transition-all"
              />
            </div>

            {/* Upload Images */}
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Images (ZIP)</label>
              <div
                onClick={() => !running && imagesRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); }}
                onDrop={(e) => { e.preventDefault(); if (!running && e.dataTransfer.files[0]) setImagesFile(e.dataTransfer.files[0]); }}
                className={`border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-accent/40 hover:bg-accent/5 transition-all ${running ? 'opacity-50 pointer-events-none' : ''}`}
              >
                <Upload size={20} className="mx-auto mb-1 text-muted" />
                <p className="text-sm text-muted">{imagesFile ? imagesFile.name : 'Click or drag images.zip'}</p>
              </div>
              <input ref={imagesRef} type="file" accept=".zip" className="hidden" onChange={(e) => setImagesFile(e.target.files?.[0] || null)} />
            </div>

            {/* Run Button */}
            <button
              onClick={handleRunInference}
              disabled={running || !selectedModel || !jobName.trim() || !imagesFile}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-accent to-primary text-white text-sm font-bold hover:brightness-110 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-all shadow-lg shadow-accent/20 flex items-center justify-center gap-2"
            >
              <Rocket size={16} />
              {running ? status : 'Run Agent Inference'}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default function AgentInferencePage() {
  return (
    <Protected>
      <AgentInferenceContent />
    </Protected>
  );
}
