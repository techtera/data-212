import JSZip from 'jszip';

export async function filesToZipBlob(files: File[]): Promise<File> {
  if (files.length === 1 && files[0].name.endsWith('.zip')) {
    return files[0];
  }
  const zip = new JSZip();
  for (const file of files) {
    zip.file(file.name, file);
  }
  const blob = await zip.generateAsync({ type: 'blob' });
  return new File([blob], 'upload.zip', { type: 'application/zip' });
}

export function describeFiles(files: File[]): string {
  if (files.length === 0) return '';
  if (files.length === 1) return files[0].name;
  return `${files.length} files selected`;
}

export const IMAGE_ACCEPT = '.zip,.png,.jpg,.jpeg,.bmp,.tiff';
export const MASK_ACCEPT = '.zip,.png,.jpg,.jpeg,.txt,.bmp';
