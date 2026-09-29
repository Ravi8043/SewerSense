import { useEffect, useRef, useState } from 'react';
import type { Summary } from '../types';
import { ErrorState, Skeleton } from './shared';

function AnimatedCount({ value }: { value: number }) {
  const [display, setDisplay] = useState(value);
  const [changed, setChanged] = useState(false);
  const previous = useRef(value);
  useEffect(() => {
    const from = previous.current;
    previous.current = value;
    if (from === value) return;
    setChanged(true);
    const started = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = Math.min(1, (now - started) / 700);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(from + (value - from) * eased));
      if (progress < 1) frame = requestAnimationFrame(step);
      else setTimeout(() => setChanged(false), 900);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <span className={`tabular-nums transition-colors duration-500 ${changed ? 'text-white' : ''}`}>{display.toLocaleString('en-IN')}</span>;
}

interface Props {
  summary: Summary | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

const KPIS: { key: keyof Summary; label: string; color: string; hint: string }[] = [
  { key: 'reports_today', label: 'Reports (24h)', color: 'text-ss-text', hint: 'Raw complaint signals received in the last 24 hours' },
  { key: 'active_incidents', label: 'Active incidents', color: 'text-ss-accent', hint: 'Open, verified or dispatched incidents' },
  { key: 'critical', label: 'Critical', color: 'text-red-400', hint: 'Active incidents with priority 80 or above' },
  { key: 'escalating', label: 'Escalating', color: 'text-orange-400', hint: 'Active incidents whose report rate is increasing or rapidly escalating' },
  { key: 'resolved', label: 'Resolved', color: 'text-emerald-400', hint: 'Incidents marked resolved' },
  { key: 'unlocated', label: 'Unlocated reports', color: 'text-ss-textmuted', hint: 'In-scope reports with no usable location, kept for review' },
];

export function KpiStrip({ summary, loading, error, onRetry }: Props) {
  if (error && !summary) {
    return (
      <div className="h-[68px] shrink-0 border-b border-ss-border bg-ss-panel">
        <ErrorState compact message={`KPIs unavailable: ${error}`} onRetry={onRetry} />
      </div>
    );
  }
  return (
    <div className="grid h-[68px] shrink-0 grid-cols-6 border-b border-ss-border bg-ss-panel" aria-live="polite">
      {KPIS.map((kpi) => (
        <div key={kpi.key} className="flex flex-col justify-center border-r border-ss-border px-5 last:border-r-0" title={kpi.hint}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ss-textmuted">{kpi.label}</div>
          <div className={`mt-0.5 text-[24px] font-bold leading-none ${kpi.color}`}>
            {loading && !summary ? <Skeleton className="mt-1 h-6 w-14" /> : summary ? <AnimatedCount value={summary[kpi.key]} /> : '—'}
          </div>
        </div>
      ))}
    </div>
  );
}
