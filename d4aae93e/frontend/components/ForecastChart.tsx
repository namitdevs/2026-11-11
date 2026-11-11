"use client";

import type { ForecastBundle } from "@/lib/types";

const W = 620;
const H = 230;
const PAD = 30;

export default function ForecastChart({ bundle }: { bundle: ForecastBundle }) {
  const slots = bundle.history.length + bundle.points.length + 1;
  const x = (index: number) => PAD + (index * (W - 2 * PAD)) / (slots - 1);
  const y = (value: number) => PAD + (1 - Math.max(0, Math.min(1.1, value)) / 1.1) * (H - 2 * PAD);
  const historyPath = bundle.history
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(point.ratio).toFixed(1)}`)
    .join(" ");
  const forecastStart = bundle.history.length + 1;
  const fanPoints = [
    ...bundle.points.map((point, index) => `${x(forecastStart + index).toFixed(1)},${y(point.p10).toFixed(1)}`),
    ...[...bundle.points].reverse().map((point, index) => `${x(forecastStart + bundle.points.length - 1 - index).toFixed(1)},${y(point.p90).toFixed(1)}`),
  ].join(" ");
  const medianPath = bundle.points
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(forecastStart + index).toFixed(1)},${y(point.p50).toFixed(1)}`)
    .join(" ");
  const lastForecast = bundle.points[bundle.points.length - 1];
  const current = bundle.history[bundle.history.length - 1];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`${bundle.label} occupancy forecast`}>
        <defs>
          <linearGradient id="fan" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#35f0b0" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#35f0b0" stopOpacity="0.03" />
          </linearGradient>
        </defs>
        {[0, 0.55, 1.1].map((tick) => (
          <g key={tick}>
            <line x1={PAD} x2={W - PAD} y1={y(tick)} y2={y(tick)} stroke="#1b2740" strokeDasharray="3 6" />
            <text x={8} y={y(tick) + 4} fill="#4b5a74" fontSize={9} fontFamily="monospace">
              {Math.round(tick * 100)}%
            </text>
          </g>
        ))}
        <line x1={x(bundle.history.length - 0.5)} x2={x(bundle.history.length - 0.5)} y1={PAD - 6} y2={H - PAD} stroke="#2a3a57" strokeDasharray="4 5" />
        <text x={x(bundle.history.length - 0.4)} y={PAD - 10} fill="#64748b" fontSize={9} fontFamily="monospace">NOW</text>
        <polygon points={fanPoints} fill="url(#fan)" stroke="#35f0b0" strokeOpacity={0.35} />
        <path d={historyPath} fill="none" stroke="#59c2ff" strokeWidth={2.6} strokeLinecap="round" />
        <path d={medianPath} fill="none" stroke="#35f0b0" strokeWidth={2.4} strokeDasharray="6 4" strokeLinecap="round" />
        {current ? <circle cx={x(bundle.history.length - 1)} cy={y(current.ratio)} r={4.5} fill="#59c2ff" stroke="#060a12" strokeWidth={2} /> : null}
        {lastForecast ? (
          <>
            <circle cx={x(forecastStart + bundle.points.length - 1)} cy={y(lastForecast.p50)} r={4.5} fill="#35f0b0" stroke="#060a12" strokeWidth={2} />
            <text x={x(forecastStart + bundle.points.length - 1) - 22} y={y(lastForecast.p50) - 12} fill="#a7f3d0" fontSize={10} fontFamily="monospace">
              {Math.round(lastForecast.p50 * 100)}%
            </text>
          </>
        ) : null}
        {bundle.points.map((point, index) => (
          <text key={point.horizon_min} x={x(forecastStart + index)} y={H - 8} fill="#64748b" fontSize={9} fontFamily="monospace" textAnchor="middle">
            +{point.horizon_min}m
          </text>
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500">
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-sky" /> observed ratio</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 border-t-2 border-dashed border-mint" /> LightGBM + XGBoost median</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-4 rounded-sm bg-mint/20" /> P10-P90 band</span>
        <span className="ml-auto mono">capacity {bundle.capacity}</span>
      </div>
    </div>
  );
}
