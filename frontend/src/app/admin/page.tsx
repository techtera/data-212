'use client';

import { useState, useRef, useEffect } from 'react';
import { adminSignModelUploads, adminRegisterModel, adminListModels, adminDeleteModel, type AdminModel } from '@/lib/api';
import { toast } from 'sonner';
import { Shield, Upload, Trash2, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function AdminPage() {
  const [adminKey, setAdminKey] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [models, setModels] = useState<AdminModel[]>([]);
  const [modelName, setModelName] = useState('');
  const [category, setCategory] = useState<'object_mask' | 'edge_mask'>('object_mask');
  const [epochs, setEpochs] = useState('10');
  const [lr, setLr] = useState('0.0001');
  const [checkpointFile, setCheckpointFile] = useState<File | null>(null);
  const [inferenceFile, setInferenceFile] = useState<File | null>(null);
  const [finetuneFile, setFinetuneFile] = useState<File | null>(null);
  const [usrInferenceFile, setUsrInferenceFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState('');
  const checkpointRef = useRef<HTMLInputElement>(null);
  const inferenceRef = useRef<HTMLInputElement>(null);
  const finetuneRef = useRef<HTMLInputElement>(null);
  const usrInferenceRef = useRef<HTMLInputElement>(null);

  const handleLogin = async () => {
    if (!adminKey.trim()) return;
    try {
      const list = await adminListModels(adminKey.trim());
      setModels(list);
      setAuthenticated(true);
    } catch {
      toast.error('Invalid admin key');
    }
  };

  const refreshModels = async () => {
    try {
      const list = await adminListModels(adminKey);
      setModels(list);
    } catch { /* ignore */ }
  };

  const uploadFile = async (url: string, file: File, contentType: string) => {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body: file,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  };

  const handleSubmit = async () => {
    if (!modelName.trim() || !checkpointFile || !inferenceFile || !finetuneFile || !usrInferenceFile) {
      toast.error('All fields and files are required');
      return;
    }

    setSubmitting(true);
    try {
      setStatus('Getting upload URLs...');
      const urls = await adminSignModelUploads(adminKey, modelName.trim());

      setStatus('Uploading checkpoint...');
      await uploadFile(urls.checkpoint_url, checkpointFile, 'application/octet-stream');

      setStatus('Uploading inference script...');
      await uploadFile(urls.inference_url, inferenceFile, 'text/x-python');

      setStatus('Uploading finetune script...');
      await uploadFile(urls.finetune_url, finetuneFile, 'text/x-python');

      setStatus('Uploading usr-inference script...');
      await uploadFile(urls.usr_inference_url, usrInferenceFile, 'text/x-python');

      setStatus('Registering model...');
      await adminRegisterModel(adminKey, {
        model_name: modelName.trim(),
        category,
        load_path: urls.gcs_paths.checkpoint,
        inference_script: urls.gcs_paths.inference,
        finetune_script: urls.gcs_paths.finetune,
        usr_inference_script: urls.gcs_paths.usr_inference,
        default_epochs: parseInt(epochs) || 10,
        default_lr: parseFloat(lr) || 0.0001,
      });

      toast.success(`Model "${modelName.trim()}" registered successfully`);
      setModelName('');
      setCheckpointFile(null);
      setInferenceFile(null);
      setFinetuneFile(null);
      setUsrInferenceFile(null);
      await refreshModels();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to register model');
    } finally {
      setSubmitting(false);
      setStatus('');
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete model "${name}"?`)) return;
    try {
      await adminDeleteModel(adminKey, name);
      toast.success(`Model "${name}" deleted`);
      await refreshModels();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="w-full max-w-sm space-y-4">
          <div className="text-center">
            <Shield size={32} className="mx-auto mb-3 text-primary" />
            <h1 className="text-xl font-bold text-foreground">Admin Access</h1>
            <p className="text-sm text-muted mt-1">Enter your admin key to manage models</p>
          </div>
          <input
            type="password"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
            placeholder="Admin API Key"
            className="w-full px-4 py-3 rounded-xl bg-card border border-border/50 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50"
          />
          <button
            onClick={handleLogin}
            className="w-full py-3 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:brightness-110 cursor-pointer transition-all"
          >
            Enter
          </button>
          <Link href="/" className="block text-center text-xs text-muted hover:text-foreground transition-colors">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const inputClass = "w-full px-3.5 py-2.5 rounded-xl bg-card/60 border border-border/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 text-foreground text-sm transition-all";

  const FileSlot = ({ label, file, inputRef, setFile }: { label: string; file: File | null; inputRef: React.RefObject<HTMLInputElement | null>; setFile: (f: File | null) => void }) => (
    <div>
      <label className="block text-xs font-semibold text-foreground/70 mb-1.5 uppercase tracking-wider">{label}</label>
      <div
        onClick={() => !submitting && inputRef.current?.click()}
        className={`border border-dashed border-border/50 rounded-xl p-3 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all ${submitting ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <Upload size={16} className="mx-auto mb-1 text-muted" />
        <p className="text-xs text-muted">{file ? file.name : `Click to upload`}</p>
      </div>
      <input ref={inputRef} type="file" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
    </div>
  );

  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-50 border-b border-border/40 bg-background/85 backdrop-blur-2xl px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield size={18} className="text-primary" />
          <span className="font-semibold text-foreground">Admin Panel</span>
        </div>
        <Link href="/" className="text-sm text-muted hover:text-foreground transition-colors flex items-center gap-1">
          <ArrowLeft size={14} />
          Dashboard
        </Link>
      </nav>

      <main className="max-w-3xl mx-auto px-8 py-10 space-y-8">
        {/* Add Model Form */}
        <div className="rounded-2xl border border-border/40 bg-card/40 p-6 space-y-5">
          <h2 className="text-lg font-bold text-foreground">Add New Model</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-1.5 uppercase tracking-wider">Model Name</label>
              <input type="text" value={modelName} onChange={(e) => setModelName(e.target.value)} disabled={submitting} placeholder="e.g. DEEPLABV3-RESNET101" className={inputClass} />
            </div>
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-1.5 uppercase tracking-wider">Category</label>
              <select value={category} onChange={(e) => setCategory(e.target.value as 'object_mask' | 'edge_mask')} disabled={submitting} className={inputClass + ' cursor-pointer'}>
                <option value="object_mask">Object Mask</option>
                <option value="edge_mask">Edge Mask</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-1.5 uppercase tracking-wider">Default Epochs</label>
              <input type="number" value={epochs} onChange={(e) => setEpochs(e.target.value)} disabled={submitting} className={inputClass} />
            </div>
            <div>
              <label className="block text-xs font-semibold text-foreground/70 mb-1.5 uppercase tracking-wider">Default Learning Rate</label>
              <input type="text" value={lr} onChange={(e) => setLr(e.target.value)} disabled={submitting} className={inputClass} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <FileSlot label="Checkpoint (.pt / .pth)" file={checkpointFile} inputRef={checkpointRef} setFile={setCheckpointFile} />
            <FileSlot label="Inference Script (.py)" file={inferenceFile} inputRef={inferenceRef} setFile={setInferenceFile} />
            <FileSlot label="Finetune Script (.py)" file={finetuneFile} inputRef={finetuneRef} setFile={setFinetuneFile} />
            <FileSlot label="Usr-Inference Script (.py)" file={usrInferenceFile} inputRef={usrInferenceRef} setFile={setUsrInferenceFile} />
          </div>

          <button
            onClick={handleSubmit}
            disabled={submitting || !modelName.trim() || !checkpointFile || !inferenceFile || !finetuneFile || !usrInferenceFile}
            className="w-full py-3 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:brightness-110 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
          >
            {submitting ? status : 'Register Model'}
          </button>
        </div>

        {/* Registered Models Table */}
        <div className="rounded-2xl border border-border/40 bg-card/40 p-6">
          <h2 className="text-lg font-bold text-foreground mb-4">Platform Models ({models.length})</h2>
          {models.length === 0 ? (
            <p className="text-sm text-muted text-center py-4">No admin-registered models yet</p>
          ) : (
            <div className="space-y-2">
              {models.map((m) => (
                <div key={m.model_name} className="flex items-center justify-between py-3 px-4 rounded-xl bg-background/50 border border-border/30">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{m.model_name}</p>
                    <p className="text-xs text-muted">{m.category === 'edge_mask' ? 'Edge Mask' : 'Object Mask'} &middot; {m.default_epochs} epochs &middot; lr={m.default_lr}</p>
                  </div>
                  <button
                    onClick={() => handleDelete(m.model_name)}
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-destructive/60 hover:text-destructive hover:bg-destructive/10 transition-all cursor-pointer"
                    title="Delete model"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
