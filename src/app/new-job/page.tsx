'use client';

import { useState, useRef } from 'react';
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
} from '@/lib/api';
import { toast } from 'sonner';
import { Upload, FlaskConical, Wrench } from 'lucide-react';

const MODELS = [
  { id: 'yolo_masking', name: 'YOLO11L Masking Model' },
];

function NewJobContent() {
  const { token } = useAuth();
  const router = useRouter();
  const [jobName, setJobName] = useState('');
  const [modelId, setModelId] = useState('yolo_masking');
  const [imagesFile, setImagesFile] = useState<File | null>(null);
  const [masksFile, setMasksFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const imagesRef = useRef<HTMLInputElement>(null);
  const masksRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (jobType: 'eval' | 'finetune') => {
    if (!imagesFile) {
      toast.error('Please select images.zip');
      return;
    }
    if (jobType === 'finetune' && !masksFile) {
      toast.error('Masks are required for fine-tuning');
      return;
    }
    if (!token) return;

    setSubmitting(true);
    setProgress(0);

    try {
      // Step 1: Get signed URLs
      setStep('Preparing upload...');
      const { dataset_id, images_upload_url, masks_upload_url } = await signUpload(token);

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
      setStep('Creating inference job...');
      setProgress(92);
      const jobData = { model_id: modelId, dataset_id, ...(jobName.trim() && { name: jobName.trim() }) };

      const job = jobType === 'eval'
        ? await createEvalJob(token, jobData)
        : await createFinetuneJob(token, jobData);

      // Step 5: Start job on VM
      setStep('Starting inference on GPU server...');
      setProgress(96);
      if (jobType === 'eval') {
        await runEval(token, job.id);
      } else {
        await runFinetune(token, job.id);
      }

      setProgress(100);
      toast.success('Inference started on GPU server');
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
              placeholder="e.g. Batch 5 - Factory Floor Images"
              className="w-full px-3 py-2 rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground"
            />
          </div>

          {/* Model Selection */}
          <div>
            <label className="block text-sm font-medium mb-1">Pretrained Model</label>
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              disabled={submitting}
              className="w-full px-3 py-2 rounded-md bg-card border border-border focus:outline-none focus:border-primary text-foreground cursor-pointer"
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
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

          {/* Submit Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => handleSubmit('eval')}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
            >
              <FlaskConical size={16} />
              Run Inference
            </button>
            <button
              disabled={!masksFile || submitting}
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
