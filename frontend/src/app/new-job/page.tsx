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
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Create New Job</h1>
          <p className="text-sm text-foreground/50 mt-1">Run inference or fine-tune a model on your data</p>
        </div>

        <div className="space-y-5">
          {/* Job Type */}
          <div>
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Task</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setJobType('eval')}
                disabled={submitting}
                className={`py-3.5 px-4 rounded-xl text-sm font-semibold border-2 transition-all cursor-pointer flex items-center justify-center gap-2 ${
                  jobType === 'eval'
                    ? 'bg-gradient-to-br from-primary/20 to-primary/5 border-primary/50 text-primary shadow-sm shadow-primary/10'
                    : 'bg-card/40 border-border/30 text-foreground/60 hover:border-border/60 hover:text-foreground/80'
                }`}
              >
                <FlaskConical size={16} />
                Inference
              </button>
              <button
                type="button"
                onClick={() => setJobType('finetune')}
                disabled={submitting}
                className={`py-3.5 px-4 rounded-xl text-sm font-semibold border-2 transition-all cursor-pointer flex items-center justify-center gap-2 ${
                  jobType === 'finetune'
                    ? 'bg-gradient-to-br from-warning/20 to-warning/5 border-warning/50 text-warning shadow-sm shadow-warning/10'
                    : 'bg-card/40 border-border/30 text-foreground/60 hover:border-border/60 hover:text-foreground/80'
                }`}
              >
                <Wrench size={16} />
                Fine-tuning
              </button>
            </div>
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
                    <div className="mx-4 mb-4">
                      <div className="rounded-xl border border-primary/20 bg-gradient-to-b from-card/60 to-card/30 overflow-hidden">
                        <div className="px-4 py-3 border-b border-border/30 flex items-center justify-between bg-primary/5">
                          <span className="text-sm font-bold text-foreground">Research Report</span>
                          <button
                            type="button"
                            onClick={() => {
                              const report = researchResult.report
                                .replace(/\$([^$]+)\$/g, (_, m) => m.replace(/\\times/g, 'x').replace(/\\text\{([^}]+)\}/g, '$1').replace(/\\/g, ''))
                                .replace(/\\times/g, 'x');
                              const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Research Report - TERAFAC</title><style>@page{margin:2cm}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:780px;margin:0 auto;padding:40px 20px;line-height:1.75;color:#1a1a2e;font-size:14px}h1{font-size:22px;color:#0f0f1a;border-bottom:2px solid #e8e8f0;padding-bottom:10px;margin-top:36px}h2{font-size:18px;color:#1a1a3e;margin-top:28px;padding-bottom:6px;border-bottom:1px solid #f0f0f5}h3{font-size:15px;color:#2a2a4e;margin-top:20px}p{margin:8px 0}ul,ol{margin:8px 0;padding-left:24px}li{margin:4px 0}table{border-collapse:collapse;width:100%;margin:16px 0;font-size:13px}th{background:#f8f8fc;font-weight:600;text-align:left;padding:10px 12px;border:1px solid #e0e0e8}td{padding:8px 12px;border:1px solid #e8e8f0}tr:nth-child(even){background:#fafafc}code{background:#f5f5fa;padding:2px 6px;border-radius:4px;font-size:12px;font-family:'SF Mono',Menlo,monospace}pre{background:#f5f5fa;padding:16px;border-radius:8px;overflow-x:auto;font-size:12px;border:1px solid #e8e8f0;white-space:pre-wrap;word-wrap:break-word}blockquote{border-left:3px solid #6366f1;margin:16px 0;padding:12px 20px;background:#f8f8ff;border-radius:0 8px 8px 0}strong{color:#0f0f2a}.header{text-align:center;margin-bottom:40px;padding-bottom:20px;border-bottom:2px solid #6366f1}.header h1{border:none;font-size:26px;color:#6366f1}.header p{color:#666;font-size:13px}</style></head><body><div class="header"><h1>TERAFAC Research Report</h1><p>Generated on ${new Date().toLocaleDateString('en-US', {year:'numeric',month:'long',day:'numeric'})}</p></div>${report.replace(/^#### (.*$)/gm,'<h4>$1</h4>').replace(/^### (.*$)/gm,'<h3>$1</h3>').replace(/^## (.*$)/gm,'<h2>$1</h2>').replace(/^# (.*$)/gm,'<h1>$1</h1>').replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/\*(.*?)\*/g,'<em>$1</em>').replace(/^- (.*$)/gm,'<li>$1</li>').replace(/(<li>.*<\/li>\n?)+/g,'<ul>$&</ul>').replace(/\`\`\`([\s\S]*?)\`\`\`/g,'<pre>$1</pre>').replace(/\`([^`]+)\`/g,'<code>$1</code>').replace(/^---$/gm,'<hr>').replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>')}</body></html>`;
                              const w = window.open('', '_blank');
                              if (w) { w.document.write(html); w.document.close(); }
                            }}
                            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:brightness-110 cursor-pointer transition-all shadow-sm shadow-primary/20"
                          >
                            Open & Save as PDF
                          </button>
                        </div>
                        <div className="px-5 py-4 max-h-[420px] overflow-y-auto text-xs text-foreground/60 leading-relaxed italic">
                          <p>Report generated successfully ({researchResult.report.length.toLocaleString()} characters). Click &quot;Open & Save as PDF&quot; to view the full formatted report in a new tab — use Ctrl+P / Cmd+P to save as PDF.</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Job Name */}
          <div>
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Job Name</label>
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
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Model Type</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setCategory('object_mask')}
                disabled={submitting}
                className={`py-3 px-4 rounded-xl text-sm font-semibold border-2 transition-all cursor-pointer ${
                  category === 'object_mask'
                    ? 'bg-gradient-to-br from-success/15 to-success/5 border-success/40 text-success shadow-sm shadow-success/10'
                    : 'bg-card/40 border-border/30 text-foreground/60 hover:border-border/60'
                }`}
              >
                Object Mask
              </button>
              <button
                type="button"
                onClick={() => setCategory('edge_mask')}
                disabled={submitting}
                className={`py-3 px-4 rounded-xl text-sm font-semibold border-2 transition-all cursor-pointer ${
                  category === 'edge_mask'
                    ? 'bg-gradient-to-br from-accent/15 to-accent/5 border-accent/40 text-accent shadow-sm shadow-accent/10'
                    : 'bg-card/40 border-border/30 text-foreground/60 hover:border-border/60'
                }`}
              >
                Edge Mask
              </button>
            </div>
          </div>

          {/* Model Selection */}
          <div>
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Model</label>
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
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Images (ZIP)</label>
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
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Masks (ZIP)</label>
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
