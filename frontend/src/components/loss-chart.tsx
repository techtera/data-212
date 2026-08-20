'use client';

interface LossChartProps {
  epochHistory: Array<Record<string, number>>;
  lossType?: string;
}

export function LossChart({ epochHistory, lossType }: LossChartProps) {
  if (!epochHistory || epochHistory.length < 2) return null;

  const trainKey = Object.keys(epochHistory[0]).find(k => k.includes('train') && k.includes('loss'));
  const valKey = Object.keys(epochHistory[0]).find(k => k.includes('val') && k.includes('loss'));

  if (!trainKey && !valKey) return null;

  const trainLosses = trainKey ? epochHistory.map(e => e[trainKey] ?? 0) : [];
  const valLosses = valKey ? epochHistory.map(e => e[valKey] ?? 0) : [];

  const allValues = [...trainLosses, ...valLosses].filter(v => v > 0);
  if (allValues.length === 0) return null;

  const maxVal = Math.max(...allValues);
  const minVal = Math.min(...allValues);
  const range = maxVal - minVal || 1;

  const width = 500;
  const height = 180;
  const padX = 40;
  const padY = 20;
  const chartW = width - padX * 2;
  const chartH = height - padY * 2;

  const toX = (i: number) => padX + (i / (epochHistory.length - 1)) * chartW;
  const toY = (v: number) => padY + (1 - (v - minVal) / range) * chartH;

  const makePath = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');

  return (
    <div className="border border-border rounded-lg p-4 bg-card">
      <h3 className="text-sm font-medium mb-2">Train / Val Loss{lossType ? ` (${lossType})` : ''}</h3>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(frac => {
          const y = padY + frac * chartH;
          const val = maxVal - frac * range;
          return (
            <g key={frac}>
              <line x1={padX} y1={y} x2={width - padX} y2={y} stroke="currentColor" strokeOpacity={0.1} />
              <text x={padX - 4} y={y + 3} textAnchor="end" fill="currentColor" fillOpacity={0.5} fontSize={9}>
                {val.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Train loss */}
        {trainLosses.length > 0 && (
          <path d={makePath(trainLosses)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
        )}

        {/* Val loss */}
        {valLosses.length > 0 && (
          <path d={makePath(valLosses)} fill="none" stroke="#f97316" strokeWidth={1.5} />
        )}

        {/* X axis label */}
        <text x={width / 2} y={height - 2} textAnchor="middle" fill="currentColor" fillOpacity={0.5} fontSize={9}>
          Epoch (1–{epochHistory.length})
        </text>
      </svg>
      <div className="flex gap-4 mt-2 text-xs text-muted">
        {trainLosses.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-blue-500 inline-block" /> Train Loss
          </span>
        )}
        {valLosses.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-orange-500 inline-block" /> Val Loss
          </span>
        )}
      </div>
    </div>
  );
}
