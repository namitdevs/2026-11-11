import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass rounded-2xl ${className}`}>{children}</div>;
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  id,
}: {
  eyebrow: string;
  title: string;
  description: string;
  id?: string;
}) {
  return (
    <div id={id} className="mb-5 scroll-mt-24">
      <div className="mono text-[10px] uppercase tracking-[0.24em] text-mint/80">{eyebrow}</div>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white md:text-3xl">{title}</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">{description}</p>
    </div>
  );
}

const toneMap: Record<string, string> = {
  mint: "border-mint/30 bg-mint/10 text-mint",
  sky: "border-sky/30 bg-sky/10 text-sky",
  amber: "border-amber/30 bg-amber/10 text-amber",
  rose: "border-rose/30 bg-rose/10 text-rose",
  slate: "border-slate-500/30 bg-slate-500/10 text-slate-300",
  violet: "border-violet-400/30 bg-violet-400/10 text-violet-300",
};

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: string }) {
  return (
    <span
      className={`mono inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${toneMap[tone] ?? toneMap.slate}`}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "text-white",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: string;
}) {
  return (
    <Card className="p-4">
      <div className="mono text-[10px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className={`mt-1.5 text-2xl font-semibold tracking-tight ${tone}`}>{value}</div>
      {sub ? <div className="mt-1 text-xs text-slate-500">{sub}</div> : null}
    </Card>
  );
}

export function Meter({ value, label, tone = "bg-mint" }: { value: number; label?: string; tone?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div>
      {label ? <div className="mb-1 flex justify-between text-[11px] text-slate-400"><span>{label}</span><span className="mono">{clamped.toFixed(0)}</span></div> : null}
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

export function PriorityBadge({ priority }: { priority: string }) {
  const tone = priority === "P0" ? "rose" : priority === "P1" ? "amber" : priority === "P2" ? "sky" : "slate";
  return <Badge tone={tone}>{priority}</Badge>;
}
