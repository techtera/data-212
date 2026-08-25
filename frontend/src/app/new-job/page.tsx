'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Protected } from '@/components/protected';
import { Navbar } from '@/components/navbar';
import {
  signUpload,
  uploadToSignedUrl,
  createEvalJob,
  createFinetuneJob,
  runEval,
  runFinetune,
  getModels,
  runResearch,
  type Model,
  type ResearchResult,
} from '@/lib/api';
import { toast } from 'sonner';
import { Upload, FlaskConical, Wrench, Search } from 'lucide-react';
import { ModelInfoCard } from '@/components/model-info-card';

function NewJobContent() {
  const { token } = useAuth();
  const router = useRouter();
  const [jobType, setJobType] = useState<'eval' | 'finetune'>('eval');
  const [jobName, setJobName] = useState('');
  const [models, setModels] = useState<Model[]>([]);
  const [category, setCategory] = useState<'object_mask' | 'edge_mask'>('object_mask');
  const [selectedModel, setSelectedModel] = useState('');
  const [imagesFile, setImagesFile] = useState<File | null>(null);
  const [masksFile, setMasksFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showModelInfo, setShowModelInfo] = useState(false);
  const [showResearch, setShowResearch] = useState(false);
  const [researchPrompt, setResearchPrompt] = useState('');
  const [researching, setResearching] = useState(false);
  const [researchResult, setResearchResult] = useState<ResearchResult | null>(null);
  const [epochs, setEpochs] = useState('');
  const [lr, setLr] = useState('');
  const imagesRef = useRef<HTMLInputElement>(null);
  const masksRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    getModels(token).then((m) => {
      setModels(m);
      const first = m.find(x => x.category === 'object_mask');
      if (first) setSelectedModel(first.model_name);
    }).catch(() => {});
  }, [token]);

  const filteredModels = models.filter(m => m.category === category);

  useEffect(() => {
    const filtered = models.filter(m => m.category === category);
    const first = filtered[0];
    if (first && !filtered.find(m => m.model_name === selectedModel)) {
      setSelectedModel(first.model_name);
    }
  }, [category, models, selectedModel]);

  const handleSubmit = async (jobType: 'eval' | 'finetune') => {
    if (!jobName.trim()) {
      toast.error('Please enter a job name');
      return;
    }
    if (!imagesFile) {
      toast.error('Please select images.zip');
      return;
    }
    if (jobType === 'finetune' && !masksFile) {
      toast.error('Masks are required for fine-tuning');
      return;
    }
    if (!token || !selectedModel) return;

    setSubmitting(true);
    setProgress(0);

    try {
      // Step 1: Get signed URLs (using job name for path)
      setStep('Preparing upload...');
      const { images_upload_url, masks_upload_url } = await signUpload(token, jobName.trim());

      // Step 2: Upload images
      setStep('Uploading images to cloud storage...');
      const progressMax = masksFile ? 50 : 90;
      await uploadToSignedUrl(images_upload_url, imagesFile, (pct) => setProgress(Math.round(pct * progressMax / 100)));

      // Step 3: Upload masks (if provided)
      if (masksFile) {
        setStep('Uploading masks to cloud storage...');
        await uploadToSignedUrl(masks_upload_url, masksFile, (pct) => setProgress(50 + Math.round(pct * 40 / 100)));
      }

      // Step 4: Create job
      setStep(jobType === 'eval' ? 'Creating inference job...' : 'Creating fine-tune job...');
      setProgress(92);
      const jobData = { model_name: selectedModel, name: jobName.trim() };

      const job = jobType === 'eval'
        ? await createEvalJob(token, jobData)
        : await createFinetuneJob(token, {
            ...jobData,
            ...(epochs ? { epochs: parseInt(epochs) } : {}),
            ...(lr ? { lr: parseFloat(lr) } : {}),
          });

      // Step 5: Start job on VM
      setStep(jobType === 'eval' ? 'Starting inference on GPU server...' : 'Starting fine-tuning on GPU server...');
      setProgress(96);
      if (jobType === 'eval') {
        await runEval(token, job.id);
      } else {
        await runFinetune(token, job.id);
      }

      setProgress(100);
      toast.success(jobType === 'eval' ? 'Inference started on GPU server' : 'Fine-tuning started on GPU server');
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create job');
      setSubmitting(false);
      setStep('');
      setProgress(0);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="max-w-2xl mx-auto px-8 py-10">
        <h1 className="text-2xl font-semibold tracking-tight mb-8">Create New Job</h1>

        <div className="space-y-5">
          {/* Job Type */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">Task</label>
            <select
              value={jobType}
              onChange={(e) => setJobType(e.target.value as 'eval' | 'finetune')}
              disabled={submitting}
              className="w-full px-3.5 py-2.5 rounded-xl bg-card/60 border border-border/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 text-foreground text-sm cursor-pointer transition-all"
            >
              <option value="eval">Inference</option>
              <option value="finetune">Fine-tuning</option>
            </select>
          </div>

          {/* Research Agent (finetune only) */}
          {jobType === 'finetune' && (
            <div>
              {!showResearch ? (
                <button
                  type="button"
                  onClick={() => setShowResearch(true)}
                  className="w-full py-2.5 px-4 rounded-xl border border-dashed border-primary/30 text-sm text-primary/80 hover:text-primary hover:border-primary/60 hover:bg-primary/5 cursor-pointer transition-all flex items-center justify-center gap-2"
                >
                  <Search size={15} />
                  Not sure which model to use? Ask AI
                </button>
              ) : (
                <div className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/80 to-card/40 backdrop-blur-sm overflow-hidden shadow-sm">
                  <div className="px-4 py-3 flex items-center justify-between border-b border-border/40">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center">
                        <Search size={12} className="text-primary" />
                      </div>
                      <span className="text-xs font-medium text-foreground/80">AI Model Advisor</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowResearch(false)}
                      className="text-xs text-muted hover:text-foreground cursor-pointer transition-colors"
                    >
                      Dismiss
                    </button>
                  </div>

                  <div className="p-4 space-y-3">
                    <textarea
                      value={researchPrompt}
                      onChange={(e) => setResearchPrompt(e.target.value)}
                      disabled={researching}
                      placeholder="Describe your images and what you want to segment...&#10;E.g.: 200 images of welded joints, need to detect weld seam boundaries"
                      className="w-full px-3 py-2.5 rounded-xl bg-background/50 border border-border/50 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 resize-none h-[68px] placeholder:text-muted/50 transition-all"
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        if (!token || !researchPrompt.trim()) return;
                        setResearching(true);
                        setResearchResult(null);
                        try {
                          const res = await runResearch(token, researchPrompt.trim());
                          setResearchResult(res);
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : 'Research failed');
                        } finally {
                          setResearching(false);
                        }
                      }}
                      disabled={researching || !researchPrompt.trim()}
                      className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-medium hover:brightness-110 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-all shadow-sm"
                    >
                      {researching ? 'Analyzing...' : 'Get Recommendation'}
                    </button>
                  </div>

                  {researchResult && (
                    <div className="mx-4 mb-4 p-3.5 rounded-xl bg-success/5 border border-success/20">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-[11px] font-medium text-success/80 uppercase tracking-wide mb-0.5">Recommended</p>
                          <p className="text-sm font-semibold text-foreground truncate">{researchResult.suggested_model}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedModel(researchResult.suggested_model);
                            const m = models.find(x => x.model_name === researchResult.suggested_model);
                            if (m) setCategory(m.category as 'object_mask' | 'edge_mask');
                            setShowResearch(false);
                            toast.success(`Model set to ${researchResult.suggested_model}`);
                          }}
                          className="shrink-0 px-3.5 py-1.5 rounded-lg bg-success text-white text-xs font-medium hover:brightness-110 cursor-pointer transition-all shadow-sm"
                        >
                          Use this
                        </button>
                      </div>
                      <p className="text-xs text-muted leading-relaxed mt-2">{researchResult.reasoning}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Job Name */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">Job Name</label>
            <input
              type="text"
              value={jobName}
              onChange={(e) => setJobName(e.target.value)}
              disabled={submitting}
              placeholder="e.g. Batch5-Factory-Floor"
              className="w-full px-3 py-2 rounded-xl bg-card/60 border border-border/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 text-foreground text-sm transition-all"
            />
            <p className="text-xs text-muted mt-1">Used as folder name in cloud storage</p>
          </div>

          {/* Model Category */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">Model Type</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setCategory('object_mask')}
                disabled={submitting}
                className={`flex-1 py-2.5 px-3 rounded-xl text-sm font-medium border transition-all cursor-pointer ${
                  category === 'object_mask'
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card border-border text-muted hover:border-primary/50'
                }`}
              >
                Object Mask
              </button>
              <button
                type="button"
                onClick={() => setCategory('edge_mask')}
                disabled={submitting}
                className={`flex-1 py-2.5 px-3 rounded-xl text-sm font-medium border transition-all cursor-pointer ${
                  category === 'edge_mask'
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card border-border text-muted hover:border-primary/50'
                }`}
              >
                Edge Mask
              </button>
            </div>
          </div>

          {/* Model Selection */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={submitting}
              className="w-full px-3 py-2 rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground cursor-pointer"
            >
              {filteredModels.map((m) => (
                <option key={m.model_name} value={m.model_name}>
                  {m.model_name}
                </option>
              ))}
            </select>
            {['YOLO11L-MASKING-MODEL', 'VGGT-SEGFORMER', 'UNETPLUSPLUS-MODEL', 'VGGT-UNETPP'].includes(selectedModel) && (
              <button
                type="button"
                onClick={() => setShowModelInfo(!showModelInfo)}
                className="mt-1 text-xs text-primary/70 hover:text-primary cursor-pointer underline underline-offset-2"
              >
                {showModelInfo ? '▾ Hide model details' : '▸ What does this model do?'}
              </button>
            )}
          </div>

          {/* Model Info Card */}
          {showModelInfo && ['YOLO11L-MASKING-MODEL', 'VGGT-SEGFORMER', 'UNETPLUSPLUS-MODEL', 'VGGT-UNETPP'].includes(selectedModel) && (
            <ModelInfoCard modelName={selectedModel} token={token} />
          )}

          {/* Images Upload */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">Images (ZIP)</label>
            <div
              onClick={() => !submitting && imagesRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (!submitting && e.dataTransfer.files[0]) setImagesFile(e.dataTransfer.files[0]); }}
              className={`border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <Upload size={20} className="mx-auto mb-1 text-muted" />
              <p className="text-sm text-muted">
                {imagesFile ? imagesFile.name : 'Click or drag images.zip here'}
              </p>
            </div>
            <input
              ref={imagesRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => setImagesFile(e.target.files?.[0] || null)}
            />
          </div>

          {/* Masks Upload (finetune only) */}
          {jobType === 'finetune' && (
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">Masks (ZIP)</label>
            <div
              onClick={() => !submitting && masksRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (!submitting && e.dataTransfer.files[0]) setMasksFile(e.dataTransfer.files[0]); }}
              className={`border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <Upload size={20} className="mx-auto mb-1 text-muted" />
              <p className="text-sm text-muted">
                {masksFile ? masksFile.name : 'Click or drag masks.zip here'}
              </p>
            </div>
            <input
              ref={masksRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => setMasksFile(e.target.files?.[0] || null)}
            />
          </div>
          )}

          {/* Progress */}
          {submitting && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted">{step}</span>
                <span className="text-foreground font-medium">{progress}%</span>
              </div>
              <div className="h-2 bg-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Advanced Settings (finetune only, hidden by default) */}
          {jobType === 'finetune' && <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              disabled={submitting}
              className="text-sm text-primary/70 hover:text-primary transition-colors cursor-pointer underline underline-offset-2"
            >
              {showAdvanced ? '▾ Hide' : '▸ Advanced Settings'}
            </button>
            {showAdvanced && (() => {
              const defaults: Record<string, { epochs: number; lr: string }> = {
                'YOLO11L-MASKING-MODEL': { epochs: 60, lr: '0.0001' },
                'VGGT-SEGFORMER': { epochs: 2, lr: '0.0001' },
                'UNETPLUSPLUS-MODEL': { epochs: 40, lr: '0.00001' },
                'VGGT-UNETPP': { epochs: 2, lr: '0.0003' },
              };
              const d = defaults[selectedModel] || { epochs: 10, lr: '0.0001' };
              return (
              <div className="mt-2 grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-muted mb-1">Epochs</label>
                  <input
                    type="number"
                    value={epochs}
                    onChange={(e) => setEpochs(e.target.value)}
                    disabled={submitting}
                    placeholder={String(d.epochs)}
                    className="w-full px-3 py-1.5 text-sm rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground placeholder:text-foreground/50"
                  />
                </div>
                <div>
                  <label className="block text-xs text-muted mb-1">Learning Rate</label>
                  <input
                    type="text"
                    value={lr}
                    onChange={(e) => setLr(e.target.value)}
                    disabled={submitting}
                    placeholder={d.lr}
                    className="w-full px-3 py-1.5 text-sm rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground placeholder:text-foreground/50"
                  />
                </div>
              </div>
              );
            })()}
          </div>}

          {/* Submit Button */}
          <div className="pt-2">
            <button
              onClick={() => handleSubmit(jobType)}
              disabled={submitting || !jobName.trim() || (jobType === 'finetune' && !masksFile)}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:brightness-110 transition-all disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed shadow-sm shadow-primary/20"
            >
              {jobType === 'eval' ? <FlaskConical size={16} /> : <Wrench size={16} />}
              {jobType === 'eval' ? 'Run Inference' : 'Start Fine-tuning'}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function NewJobPage() {
  return (
    <Protected>
      <NewJobContent />
    </Protected>
  );
}
