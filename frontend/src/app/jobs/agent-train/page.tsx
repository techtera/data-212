'use client';

import { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Protected } from '@/components/protected';
import { Navbar } from '@/components/navbar';
import { signUpload, uploadToSignedUrl, runResearch, generateTrainingCode, createFinetuneJob, runAgentTrain } from '@/lib/api';
import { toast } from 'sonner';
import { ArrowLeft, Search, Upload, Rocket } from 'lucide-react';
import Link from 'next/link';

type Step = 'research' | 'upload' | 'training';

function AgentTrainContent() {
  const { token } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState<Step>('research');
  const [prompt, setPrompt] = useState('');
  const [researching, setResearching] = useState(false);
  const [report, setReport] = useState('');
  const [jobName, setJobName] = useState('');
  const [maskType, setMaskType] = useState<'object' | 'edge'>('object');
  const [imagesFile, setImagesFile] = useState<File | null>(null);
  const [masksFile, setMasksFile] = useState<File | null>(null);
  const [training, setTraining] = useState(false);
  const [trainingStatus, setTrainingStatus] = useState('');
  const imagesRef = useRef<HTMLInputElement>(null);
  const masksRef = useRef<HTMLInputElement>(null);

  const handleResearch = async () => {
    if (!token || !prompt.trim()) return;
    setResearching(true);
    try {
      const res = await runResearch(token, prompt.trim());
      setReport(res.report);
      setStep('upload');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Research failed');
    } finally {
      setResearching(false);
    }
  };

  const handleStartTraining = async () => {
    if (!token || !jobName.trim() || !imagesFile || !masksFile) return;
    setTraining(true);

    try {
      // Step 1: Generate training code
      setTrainingStatus('AI is writing training code...');
      const codeRes = await generateTrainingCode(token, report, jobName.trim(), maskType);

      // Step 2: Upload data
      setTrainingStatus('Uploading images...');
      const urls = await signUpload(token, jobName.trim());
      await uploadToSignedUrl(urls.images_upload_url, imagesFile);

      setTrainingStatus('Uploading masks...');
      await uploadToSignedUrl(urls.masks_upload_url, masksFile);

      // Step 3: Create finetune job and start
      setTrainingStatus('Starting training on GPU server...');
      const job = await createFinetuneJob(token, { model_name: codeRes.model_name, name: jobName.trim() });
      await runAgentTrain(token, job.id);

      toast.success('Training started! Redirecting to job page...');
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Training failed to start');
      setTraining(false);
      setTrainingStatus('');
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
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Train with AI Agent</h1>
          <p className="text-sm text-foreground/50 mt-1">Describe your task → AI suggests architecture → train automatically</p>
        </div>

        {/* Progress indicator */}
        <div className="flex items-center gap-2 mb-8">
          {(['research', 'upload', 'training'] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                step === s ? 'bg-primary text-white' :
                (['research', 'upload', 'training'].indexOf(step) > i) ? 'bg-success/20 text-success' :
                'bg-card border border-border text-muted'
              }`}>
                {i + 1}
              </div>
              <span className={`text-xs font-medium ${step === s ? 'text-foreground' : 'text-muted'}`}>
                {s === 'research' ? 'Research' : s === 'upload' ? 'Upload Data' : 'Train'}
              </span>
              {i < 2 && <div className="w-8 h-px bg-border" />}
            </div>
          ))}
        </div>

        {/* Step 1: Research */}
        {step === 'research' && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-border/40 bg-card/40 p-6">
              <div className="flex items-center gap-2 mb-4">
                <Search size={18} className="text-primary" />
                <h2 className="text-base font-semibold">Describe your segmentation task</h2>
              </div>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={researching}
                placeholder="E.g.: I have 300 images of steel pipes with welding defects. I need to segment the weld seam boundaries and detect micro-cracks (porosity, hairline fractures). Images are 1280x720 from industrial cameras."
                className="w-full px-4 py-3 rounded-xl bg-background/50 border border-border/50 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 resize-none h-28 placeholder:text-muted/50 transition-all"
              />
              <button
                onClick={handleResearch}
                disabled={researching || !prompt.trim()}
                className="mt-3 w-full py-3 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:brightness-110 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-all shadow-sm"
              >
                {researching ? 'AI is researching architectures...' : 'Get Architecture Recommendation'}
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Upload */}
        {step === 'upload' && (
          <div className="space-y-5">
            {/* Architecture summary */}
            <div className="rounded-2xl border border-success/20 bg-gradient-to-br from-success/10 to-success/5 p-5">
              <p className="text-xs font-semibold text-success uppercase tracking-wider mb-2">Recommended Architecture</p>
              <p className="text-lg font-bold text-foreground">
                {(() => {
                  const archLine = report.split('\n').find(l => l.startsWith('ARCHITECTURE:'));
                  return archLine ? archLine.replace('ARCHITECTURE:', '').trim() : report.split('\n').find(l => l.includes('Recommended'))?.slice(0, 80) || 'Custom Architecture';
                })()}
              </p>
              <div className="flex gap-3 mt-3">
                <button
                  onClick={() => {
                    const w = window.open('', '_blank');
                    if (w) { w.document.write(`<pre style="font-family:system-ui;max-width:800px;margin:40px auto;line-height:1.7;white-space:pre-wrap">${report}</pre>`); w.document.close(); }
                  }}
                  className="text-xs text-primary cursor-pointer hover:underline"
                >
                  View full report
                </button>
                <button
                  onClick={() => {
                    const blob = new Blob([report], { type: 'text/markdown' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'research_report.md';
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="text-xs text-success cursor-pointer hover:underline"
                >
                  Download Report
                </button>
                <Link href="/new-job" className="text-xs text-muted cursor-pointer hover:text-foreground hover:underline">
                  Back to normal inference/finetune
                </Link>
              </div>
            </div>

            {/* Job name */}
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Job Name</label>
              <input
                type="text"
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
                placeholder="e.g. weld-defect-segformer"
                className="w-full px-3.5 py-2.5 rounded-xl bg-card/60 border border-border/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 text-foreground text-sm transition-all"
              />
            </div>

            {/* Mask type */}
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Mask Type</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setMaskType('object')}
                  className={`py-3 px-4 rounded-xl text-sm font-semibold border-2 transition-all cursor-pointer ${
                    maskType === 'object'
                      ? 'bg-gradient-to-br from-success/15 to-success/5 border-success/40 text-success'
                      : 'bg-card/40 border-border/30 text-foreground/60'
                  }`}
                >
                  Object (.txt YOLO)
                </button>
                <button
                  type="button"
                  onClick={() => setMaskType('edge')}
                  className={`py-3 px-4 rounded-xl text-sm font-semibold border-2 transition-all cursor-pointer ${
                    maskType === 'edge'
                      ? 'bg-gradient-to-br from-accent/15 to-accent/5 border-accent/40 text-accent'
                      : 'bg-card/40 border-border/30 text-foreground/60'
                  }`}
                >
                  Edge (_mask.png)
                </button>
              </div>
            </div>

            {/* Upload images */}
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Images (ZIP)</label>
              <div
                onClick={() => imagesRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); }}
                onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files[0]) setImagesFile(e.dataTransfer.files[0]); }}
                className="border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all"
              >
                <Upload size={20} className="mx-auto mb-1 text-muted" />
                <p className="text-sm text-muted">{imagesFile ? imagesFile.name : 'Click or drag images.zip'}</p>
              </div>
              <input ref={imagesRef} type="file" accept=".zip" className="hidden" onChange={(e) => setImagesFile(e.target.files?.[0] || null)} />
            </div>

            {/* Upload masks */}
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Masks (ZIP)</label>
              <div
                onClick={() => masksRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); }}
                onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files[0]) setMasksFile(e.dataTransfer.files[0]); }}
                className="border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all"
              >
                <Upload size={20} className="mx-auto mb-1 text-muted" />
                <p className="text-sm text-muted">{masksFile ? masksFile.name : 'Click or drag masks.zip'}</p>
              </div>
              <input ref={masksRef} type="file" accept=".zip" className="hidden" onChange={(e) => setMasksFile(e.target.files?.[0] || null)} />
            </div>

            {/* Start training */}
            <button
              onClick={handleStartTraining}
              disabled={training || !jobName.trim() || !imagesFile || !masksFile}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-primary to-success text-white text-sm font-bold hover:brightness-110 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2"
            >
              <Rocket size={16} />
              {training ? trainingStatus : 'Start Training'}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default function AgentTrainPage() {
  return (
    <Protected>
      <AgentTrainContent />
    </Protected>
  );
}
