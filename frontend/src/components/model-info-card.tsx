'use client';

import { useEffect, useState } from 'react';
import { getModelViz } from '@/lib/api';

const MODEL_DESC: Record<string, { desc: string; inputFormat: string }> = {
  'YOLO11L-MASKING-MODEL': {
    desc: 'Detects and segments objects (weld pieces, industrial parts) in images. Draws colored mask overlays on detected regions.',
    inputFormat: 'Images: .zip of PNG/JPG files. Masks (finetune): .zip of YOLO .txt label files (polygon coordinates, same filename as image).',
  },
  'VGGT-SEGFORMER': {
    desc: 'Segments objects using a large vision transformer. Produces red mask overlays on detected object regions. Best for complex scenes.',
    inputFormat: 'Images: .zip of PNG/JPG files. Masks (finetune): .zip of YOLO .txt label files (polygon coordinates, same filename as image).',
  },
  'UNETPLUSPLUS-MODEL': {
    desc: 'Detects edges and boundaries in images. Produces thin green edge overlays — useful for measuring contours, weld seams, and part boundaries.',
    inputFormat: 'Images: .zip of PNG/JPG files. Masks (finetune): .zip of binary PNG edge masks (filename: imagename_mask.png).',
  },
  'VGGT-UNETPP': {
    desc: 'Detects edges using a large vision transformer backbone. Produces green edge overlays — higher accuracy than UNet++ on complex geometries.',
    inputFormat: 'Images: .zip of PNG/JPG files. Masks (finetune): .zip of binary PNG edge masks (filename: imagename_mask.png).',
  },
};

interface Props {
  modelName: string;
  token: string | null;
}

export function ModelInfoCard({ modelName, token }: Props) {
  const [viz, setViz] = useState<{ inputs: string[]; outputs: string[] } | null>(null);

  useEffect(() => {
    if (!token || !modelName) return;
    setViz(null);
    getModelViz(token, modelName).then(setViz).catch(() => {});
  }, [token, modelName]);

  const info = MODEL_DESC[modelName];
  if (!info) return null;

  return (
    <div className="border border-border rounded-lg p-4 bg-card mt-2 space-y-3">
      <p className="text-sm text-foreground">{info.desc}</p>
      <div>
        <p className="text-xs text-muted font-medium mb-1">Input Format:</p>
        <p className="text-xs text-muted">{info.inputFormat}</p>
      </div>
      {viz && viz.inputs.length > 0 && (
        <div>
          <p className="text-xs text-muted font-medium mb-2">Sample Input → Output:</p>
          <div className="grid grid-cols-2 gap-2">
            {viz.inputs.map((url, i) => (
              <div key={i} className="space-y-1">
                <img src={url} alt={`Input ${i+1}`} className="w-full h-24 object-cover rounded border border-border" loading="lazy" />
                {viz.outputs[i] && (
                  <img src={viz.outputs[i]} alt={`Output ${i+1}`} className="w-full h-24 object-cover rounded border border-primary/30" loading="lazy" />
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted mt-1">Top: input image. Bottom: model prediction.</p>
        </div>
      )}
    </div>
  );
}
