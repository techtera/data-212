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
  type Model,
} from '@/lib/api';
import { toast } from 'sonner';
import { Upload, FlaskConical, Wrench, Search } from 'lucide-react';
import Link from 'next/link';
import { filesToZipBlob, describeFiles, IMAGE_ACCEPT, MASK_ACCEPT } from '@/lib/zip-utils';
import { ModelInfoCard } from '@/components/model-info-card';

function NewJobContent() {
  const { token } = useAuth();
  const router = useRouter();
  const [jobType, setJobType] = useState<'eval' | 'finetune'>('eval');
  const [jobName, setJobName] = useState('');
  const [models, setModels] = useState<Model[]>([]);
  const [category, setCategory] = useState<'object_mask' | 'edge_mask'>('object_mask');
  const [selectedModel, setSelectedModel] = useState('');
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [maskFiles, setMaskFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showModelInfo, setShowModelInfo] = useState(false);
  const [epochs, setEpochs] = useState('');
  const [lr, setLr] = useState('');
  const [lrEncoder, setLrEncoder] = useState('');
  const [lrDecoder, setLrDecoder] = useState('');
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

  const filteredModels = models.filter(m => {
    if (m.category !== category) return false;
    if (m.is_agent) return false;
    return true;
  });

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
    if (imageFiles.length === 0) {
      toast.error('Please select images (zip or individual files)');
      return;
    }
    if (jobType === 'finetune' && maskFiles.length === 0) {
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

      // Step 2: Zip if needed + upload images
      setStep(imageFiles.length > 1 ? 'Zipping & uploading images...' : 'Uploading images to cloud storage...');
      const imagesZip = await filesToZipBlob(imageFiles);
      const hasMasks = maskFiles.length > 0;
      const progressMax = hasMasks ? 50 : 90;
      await uploadToSignedUrl(images_upload_url, imagesZip, (pct) => setProgress(Math.round(pct * progressMax / 100)));

      // Step 3: Upload masks (if provided)
      if (hasMasks) {
        setStep(maskFiles.length > 1 ? 'Zipping & uploading masks...' : 'Uploading masks to cloud storage...');
        const masksZip = await filesToZipBlob(maskFiles);
        await uploadToSignedUrl(masks_upload_url, masksZip, (pct) => setProgress(50 + Math.round(pct * 40 / 100)));
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
            ...(lrEncoder ? { lr_encoder: parseFloat(lrEncoder) } : {}),
            ...(lrDecoder ? { lr_decoder: parseFloat(lrDecoder) } : {}),
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

          {/* AI Agent links */}
          {jobType === 'finetune' && (
            <Link
              href="/jobs/agent-train"
              className="w-full py-2.5 px-4 rounded-xl border border-dashed border-primary/30 text-sm text-primary/80 hover:text-primary hover:border-primary/60 hover:bg-primary/5 transition-all flex items-center justify-center gap-2"
            >
              <Search size={15} />
              Want to train a new architecture? Use AI Agent
            </Link>
          )}
          {jobType === 'eval' && (
            <Link
              href="/jobs/agent-inference"
              className="w-full py-2.5 px-4 rounded-xl border border-dashed border-accent/30 text-sm text-accent/80 hover:text-accent hover:border-accent/60 hover:bg-accent/5 transition-all flex items-center justify-center gap-2"
            >
              <FlaskConical size={15} />
              Have an AI-trained model? Run Agent Inference
            </Link>
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
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Images (ZIP or individual files)</label>
            <div
              onClick={() => !submitting && imagesRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (!submitting && e.dataTransfer.files.length) setImageFiles(Array.from(e.dataTransfer.files)); }}
              className={`border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <Upload size={20} className="mx-auto mb-1 text-muted" />
              <p className="text-sm text-muted">
                {imageFiles.length > 0 ? describeFiles(imageFiles) : 'Click or drag images (.zip or .png/.jpg)'}
              </p>
            </div>
            <input
              ref={imagesRef}
              type="file"
              accept={IMAGE_ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => setImageFiles(e.target.files ? Array.from(e.target.files) : [])}
            />
          </div>

          {/* Masks Upload (finetune only) */}
          {jobType === 'finetune' && (
          <div>
            <label className="block text-xs font-semibold text-foreground/70 mb-2 uppercase tracking-wider">Masks (ZIP or individual files)</label>
            <div
              onClick={() => !submitting && masksRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (!submitting && e.dataTransfer.files.length) setMaskFiles(Array.from(e.dataTransfer.files)); }}
              className={`border border-dashed border-border/50 rounded-xl p-5 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <Upload size={20} className="mx-auto mb-1 text-muted" />
              <p className="text-sm text-muted">
                {maskFiles.length > 0 ? describeFiles(maskFiles) : 'Click or drag masks (.zip, .png, or .txt)'}
              </p>
            </div>
            <input
              ref={masksRef}
              type="file"
              accept={MASK_ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => setMaskFiles(e.target.files ? Array.from(e.target.files) : [])}
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
              const isUnetpp = selectedModel === 'UNETPLUSPLUS-MODEL';
              const defaults: Record<string, { epochs: number; lr?: string; lr_enc?: string; lr_dec?: string }> = {
                'YOLO11L-MASKING-MODEL': { epochs: 60, lr: '0.0001' },
                'VGGT-SEGFORMER': { epochs: 2, lr: '0.0001' },
                'UNETPLUSPLUS-MODEL': { epochs: 40, lr_enc: '0.00001', lr_dec: '0.00005' },
                'VGGT-UNETPP': { epochs: 2, lr: '0.0003' },
              };
              const d = defaults[selectedModel] || { epochs: 10, lr: '0.0001' };
              const inputClass = "w-full px-3 py-1.5 text-sm rounded-xl bg-card/60 border border-border/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 text-foreground placeholder:text-foreground/50 transition-all";
              return (
              <div className="mt-2 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-muted mb-1">Epochs</label>
                    <input type="number" value={epochs} onChange={(e) => setEpochs(e.target.value)} disabled={submitting} placeholder={String(d.epochs)} className={inputClass} />
                  </div>
                  {!isUnetpp && (
                    <div>
                      <label className="block text-xs text-muted mb-1">Learning Rate</label>
                      <input type="text" value={lr} onChange={(e) => setLr(e.target.value)} disabled={submitting} placeholder={d.lr || '0.0001'} className={inputClass} />
                    </div>
                  )}
                </div>
                {isUnetpp && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-muted mb-1">LR Encoder</label>
                      <input type="text" value={lrEncoder} onChange={(e) => setLrEncoder(e.target.value)} disabled={submitting} placeholder={d.lr_enc || '0.00001'} className={inputClass} />
                    </div>
                    <div>
                      <label className="block text-xs text-muted mb-1">LR Decoder</label>
                      <input type="text" value={lrDecoder} onChange={(e) => setLrDecoder(e.target.value)} disabled={submitting} placeholder={d.lr_dec || '0.00005'} className={inputClass} />
                    </div>
                  </div>
                )}
              </div>
              );
            })()}
          </div>}

          {/* Submit Button */}
          <div className="pt-2">
            <button
              onClick={() => handleSubmit(jobType)}
              disabled={submitting || !jobName.trim() || imageFiles.length === 0 || (jobType === 'finetune' && maskFiles.length === 0)}
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
