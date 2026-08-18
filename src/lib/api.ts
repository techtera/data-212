const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `Request failed: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export function register(data: { username: string; email: string; password: string }) {
  return request<{ id: string; username: string; email: string }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function login(data: { username: string; password: string }) {
  return request<{ token: string; user: { id: string; username: string; email: string } }>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify(data) }
  );
}

export function logout(token: string) {
  return request<void>('/auth/logout', { method: 'POST' }, token);
}

export function getMe(token: string) {
  return request<{ id: string; username: string; email: string }>('/auth/me', {}, token);
}

// Models
export interface Model {
  model_name: string;
  load_path: string;
  inference_script: string;
  save_path: string;
  user_id: string;
}

export function getModels(token: string) {
  return request<Model[]>('/models', {}, token);
}

// Jobs
export interface Job {
  id: string;
  name: string | null;
  job_type: 'eval' | 'finetune';
  status: 'uploading' | 'running' | 'done' | 'error';
  model_name: string;
  created_at: string;
  error_message?: string;
}

export function getJobs(token: string) {
  return request<Job[]>('/jobs', {}, token);
}

export function createEvalJob(
  token: string,
  data: { model_name: string; name: string }
) {
  return request<{ id: string; status: string }>('/jobs/eval', {
    method: 'POST',
    body: JSON.stringify(data),
  }, token);
}

export function createFinetuneJob(
  token: string,
  data: { model_name: string; name: string }
) {
  return request<{ id: string; status: string }>('/jobs/finetune', {
    method: 'POST',
    body: JSON.stringify(data),
  }, token);
}

// Uploads
export function signUpload(token: string, jobName: string) {
  return request<{ job_name: string; images_upload_url: string; masks_upload_url: string }>(
    '/uploads/sign',
    { method: 'POST', body: JSON.stringify({ job_name: jobName }) },
    token
  );
}

export async function uploadToSignedUrl(
  url: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.setRequestHeader('Content-Type', 'application/zip');

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed: ${xhr.status}`));
    };

    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.send(file);
  });
}

// Job actions
export function runEval(token: string, jobId: string) {
  return request<{ status: string }>(`/jobs/${jobId}/run-eval`, { method: 'POST' }, token);
}

export function runFinetune(token: string, jobId: string) {
  return request<{ status: string }>(`/jobs/${jobId}/run-finetune`, { method: 'POST' }, token);
}

// Results
export function getResults(token: string, jobId: string) {
  return request<{ prediction_urls: string[] }>(
    `/jobs/${jobId}/results`,
    {},
    token
  );
}

export function getDownload(token: string, jobId: string) {
  return request<{ checkpoint_url: string | null; inference_script_url: string | null }>(
    `/jobs/${jobId}/download`,
    {},
    token
  );
}
