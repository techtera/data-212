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
import { Upload, FlaskConical, Wrench } from 'lucide-react';

function NewJobContent() {
  const { token } = useAuth();
  const router = useRouter();
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
      <main className="max-w-lg mx-auto px-4 py-8">
        <h1 className="text-xl font-semibold mb-6">Create New Job</h1>

        <div className="space-y-5">
          {/* Job Name */}
          <div>
            <label className="block text-sm font-medium mb-1">Job Name</label>
            <input
              type="text"
              value={jobName}
              onChange={(e) => setJobName(e.target.value)}
              disabled={submitting}
              placeholder="e.g. Batch5-Factory-Floor"
              className="w-full px-3 py-2 rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground"
            />
            <p className="text-xs text-muted mt-1">Used as folder name in cloud storage</p>
          </div>

          {/* Model Category */}
          <div>
            <label className="block text-sm font-medium mb-1">Model Type</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setCategory('object_mask')}
                disabled={submitting}
                className={`flex-1 py-2 px-3 rounded-md text-sm font-medium border transition-colors cursor-pointer ${
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
                className={`flex-1 py-2 px-3 rounded-md text-sm font-medium border transition-colors cursor-pointer ${
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
            <label className="block text-sm font-medium mb-1">Model</label>
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
          </div>

          {/* Images Upload */}
          <div>
            <label className="block text-sm font-medium mb-1">Images (ZIP)</label>
            <div
              onClick={() => !submitting && imagesRef.current?.click()}
              className={`border border-dashed border-border rounded-md p-4 text-center cursor-pointer hover:border-primary/50 transition-colors ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <Upload size={20} className="mx-auto mb-1 text-muted" />
              <p className="text-sm text-muted">
                {imagesFile ? imagesFile.name : 'Click to select images.zip'}
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

          {/* Masks Upload (Optional) */}
          <div>
            <label className="block text-sm font-medium mb-1">Masks (ZIP) <span className="text-muted text-xs font-normal">— optional for inference</span></label>
            <div
              onClick={() => !submitting && masksRef.current?.click()}
              className={`border border-dashed border-border rounded-md p-4 text-center cursor-pointer hover:border-primary/50 transition-colors ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <Upload size={20} className="mx-auto mb-1 text-muted" />
              <p className="text-sm text-muted">
                {masksFile ? masksFile.name : 'Click to select masks.zip (optional)'}
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

          {/* Advanced Settings (hidden by default) */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              disabled={submitting}
              className="text-sm text-primary/70 hover:text-primary transition-colors cursor-pointer underline underline-offset-2"
            >
              {showAdvanced ? '▾ Hide' : '▸ Advanced Settings'}
            </button>
            {showAdvanced && (
              <div className="mt-2 grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-muted mb-1">Epochs</label>
                  <input
                    type="number"
                    value={epochs}
                    onChange={(e) => setEpochs(e.target.value)}
                    disabled={submitting}
                    placeholder="default"
                    className="w-full px-3 py-1.5 text-sm rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground"
                  />
                </div>
                <div>
                  <label className="block text-xs text-muted mb-1">Learning Rate</label>
                  <input
                    type="text"
                    value={lr}
                    onChange={(e) => setLr(e.target.value)}
                    disabled={submitting}
                    placeholder="default"
                    className="w-full px-3 py-1.5 text-sm rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Submit Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => handleSubmit('eval')}
              disabled={submitting || !jobName.trim()}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
            >
              <FlaskConical size={16} />
              Run Inference
            </button>
            <button
              disabled={!masksFile || submitting || !jobName.trim()}
              onClick={() => handleSubmit('finetune')}
              title={!masksFile ? 'Upload masks to enable fine-tuning' : 'Fine-tuning coming soon'}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-md bg-warning/20 text-warning border border-warning/30 font-medium disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
            >
              <Wrench size={16} />
              Fine-tune {!masksFile && '(needs masks)'}
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
