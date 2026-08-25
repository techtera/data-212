'use client';

import { useState } from 'react';

interface LossChartProps {
  epochHistory: Array<Record<string, number>>;
  lossType?: string;
}

export function LossChart({ epochHistory, lossType }: LossChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

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

  const width = 560;
  const height = 200;
  const padX = 48;
  const padY = 24;
  const chartW = width - padX * 2;
  const chartH = height - padY * 2;

  const toX = (i: number) => padX + (i / (epochHistory.length - 1)) * chartW;
  const toY = (v: number) => padY + (1 - (v - minVal) / range) * chartH;

  const makePath = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');

  const hoverData = hoverIdx !== null ? {
    epoch: hoverIdx + 1,
    train: trainLosses[hoverIdx],
    val: valLosses[hoverIdx],
    x: toX(hoverIdx),
    y: Math.min(toY(trainLosses[hoverIdx] || 0), toY(valLosses[hoverIdx] || 0)),
  } : null;

  return (
    <div className="border border-border/40 rounded-2xl p-5 bg-card/40">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground">Training Loss{lossType ? ` — ${lossType}` : ''}</h3>
        <div className="flex gap-4 text-xs">
          {trainLosses.length > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-[3px] rounded-full bg-[#60a5fa] inline-block" /> Train
            </span>
          )}
          {valLosses.length > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-[3px] rounded-full bg-[#f97316] inline-block" /> Val
            </span>
          )}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map(frac => {
          const y = padY + frac * chartH;
          const val = maxVal - frac * range;
          return (
            <g key={frac}>
              <line x1={padX} y1={y} x2={width - padX} y2={y} stroke="currentColor" strokeOpacity={0.06} />
              <text x={padX - 6} y={y + 3} textAnchor="end" fill="currentColor" fillOpacity={0.4} fontSize={10}>
                {val.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Train line */}
        {trainLosses.length > 0 && (
          <path d={makePath(trainLosses)} fill="none" stroke="#60a5fa" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* Val line */}
        {valLosses.length > 0 && (
          <path d={makePath(valLosses)} fill="none" stroke="#f97316" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* Hover zones */}
        {epochHistory.map((_, i) => (
          <rect
            key={i}
            x={toX(i) - chartW / epochHistory.length / 2}
            y={padY}
            width={chartW / epochHistory.length}
            height={chartH}
            fill="transparent"
            onMouseEnter={() => setHoverIdx(i)}
          />
        ))}

        {/* Hover indicator */}
        {hoverData && (
          <>
            <line x1={hoverData.x} y1={padY} x2={hoverData.x} y2={padY + chartH} stroke="currentColor" strokeOpacity={0.15} strokeDasharray="3 3" />
            {trainLosses[hoverIdx!] !== undefined && (
              <>
                <circle cx={hoverData.x} cy={toY(trainLosses[hoverIdx!])} r={5} fill="#60a5fa" fillOpacity={0.3} />
                <circle cx={hoverData.x} cy={toY(trainLosses[hoverIdx!])} r={3} fill="#60a5fa" />
                <text x={hoverData.x + 6} y={toY(trainLosses[hoverIdx!]) - 6} fill="#60a5fa" fontSize={9} fontWeight="600">
                  {trainLosses[hoverIdx!].toFixed(3)}
                </text>
              </>
            )}
            {valLosses[hoverIdx!] !== undefined && (
              <>
                <circle cx={hoverData.x} cy={toY(valLosses[hoverIdx!])} r={5} fill="#f97316" fillOpacity={0.3} />
                <circle cx={hoverData.x} cy={toY(valLosses[hoverIdx!])} r={3} fill="#f97316" />
                <text x={hoverData.x + 6} y={toY(valLosses[hoverIdx!]) + 12} fill="#f97316" fontSize={9} fontWeight="600">
                  {valLosses[hoverIdx!].toFixed(3)}
                </text>
              </>
            )}
          </>
        )}

        {/* X axis */}
        <text x={width / 2} y={height - 4} textAnchor="middle" fill="currentColor" fillOpacity={0.35} fontSize={10}>
          Epoch (1–{epochHistory.length})
        </text>
      </svg>

      {hoverData && (
        <p className="text-xs text-muted mt-1">Epoch {hoverData.epoch}</p>
      )}
    </div>
  );
}
