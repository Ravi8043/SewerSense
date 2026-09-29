import React, { useEffect, useRef } from 'react';
import type { Band, ConfidenceLabel, GeoQuality, Source, Status, VelocityLabel } from '../types';

export const BAND_COLORS: Record<Band, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#f59e0b',
  LOW: '#64748b',
};

export const SOURCE_META: Record<Source, { label: string; color: string; icon: string }> = {
  phone: { label: 'Phone', color: '#60a5fa', icon: 'M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z' },
  social: { label: 'Social', color: '#a78bfa', icon: 'M4 4h16v12H7l-3 3z' },
  whatsapp: { label: 'WhatsApp', color: '#34d399', icon: 'M12 3a9 9 0 0 0-7.8 13.5L3 21l4.6-1.2A9 9 0 1 0 12 3z' },
  news: { label: 'News', color: '#fb923c', icon: 'M4 5h13v14H6a2 2 0 0 1-2-2zm13 4h3v8a2 2 0 0 1-2 2M7 9h7M7 13h7' },
  official: { label: 'Official portal', color: '#f472b6', icon: 'M12 3 4 7v2h16V7zM6 11v6m4-6v6m4-6v6m4-6v6M4 20h16' },
  field: { label: 'Field officer', color: '#22d3ee', icon: 'M12 2a6 6 0 0 0-6 6c0 4.5 6 12 6 12s6-7.5 6-12a6 6 0 0 0-6-6zm0 8.5A2.5 2.5 0 1 1 12 5.5a2.5 2.5 0 0 1 0 5z' },
};

export const GEO_LABELS: Record<GeoQuality, string> = {
  exact: 'Exact point',
  road: 'Road-level',
  locality: 'Locality only',
  none: 'Unlocated',
};

export const STATUS_LABELS: Record<Status, string> = {
  open: 'Open',
  verified: 'Verified',
  dispatched: 'Dispatched',
  resolved: 'Resolved',
};

export const categoryLabel = (category: string) => {
  const text = category.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
};

export const Skeleton = ({ className = '' }: { className?: string }) => <div className={`animate-pulse rounded bg-ss-border/70 ${className}`} aria-hidden="true" />;

export const PriorityBadge = ({ band, priority, size = 'sm' }: { band: Band; priority: number; size?: 'sm' | 'md' }) => (
  <span
    className={`inline-flex items-center gap-1 rounded border font-semibold tabular-nums ${size === 'md' ? 'px-2 py-0.5 text-[12px]' : 'px-1.5 py-px text-[11px]'}`}
    style={{ color: BAND_COLORS[band], borderColor: `${BAND_COLORS[band]}66`, background: `${BAND_COLORS[band]}1f` }}
    title={`Priority ${priority} (${band})`}
  >
    <span>{priority}</span>
    <span className="text-[10px] tracking-wide opacity-90">{band}</span>
  </span>
);

const VELOCITY_STYLE: Record<VelocityLabel, { color: string; arrow: string; short: string }> = {
  'RAPIDLY ESCALATING': { color: '#ef4444', arrow: '⇈', short: 'Rapidly escalating' },
  INCREASING: { color: '#f97316', arrow: '↑', short: 'Increasing' },
  STEADY: { color: '#94a3b8', arrow: '→', short: 'Steady' },
  DECLINING: { color: '#38bdf8', arrow: '↓', short: 'Declining' },
};

export const VelocityBadge = ({ label }: { label: VelocityLabel }) => {
  const style = VELOCITY_STYLE[label];
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap text-[12px] font-medium" style={{ color: style.color }}>
      <span aria-hidden="true">{style.arrow}</span>
      {style.short}
    </span>
  );
};

export const StatusPill = ({ status }: { status: Status }) => {
  const colors: Record<Status, string> = {
    open: 'text-ss-textmuted border-ss-border',
    verified: 'text-sky-300 border-sky-400/40 bg-sky-400/10',
    dispatched: 'text-violet-300 border-violet-400/40 bg-violet-400/10',
    resolved: 'text-emerald-300 border-emerald-400/40 bg-emerald-400/10',
  };
  return <span className={`rounded border px-1.5 py-px text-[11px] font-medium ${colors[status]}`}>{STATUS_LABELS[status]}</span>;
};

export const ConfidencePill = ({ label }: { label: ConfidenceLabel }) => {
  const color = label === 'HIGH' ? '#34d399' : label === 'MEDIUM' ? '#fbbf24' : '#f87171';
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] font-medium" style={{ color }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} aria-hidden="true" />
      {label.charAt(0) + label.slice(1).toLowerCase()} confidence
    </span>
  );
};

export const SourceIcon = ({ source, className = 'h-3.5 w-3.5' }: { source: Source; className?: string }) => (
  <svg viewBox="0 0 24 24" className={className} fill="none" stroke={SOURCE_META[source].color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={SOURCE_META[source].icon} />
  </svg>
);

export const ErrorState = ({ message, onRetry, compact = false }: { message: string; onRetry?: () => void; compact?: boolean }) => (
  <div role="alert" className={`flex ${compact ? 'flex-row gap-3' : 'flex-col gap-3 p-6'} h-full w-full items-center justify-center text-center`}>
    <div className="text-[13px] text-red-300">{message}</div>
    {onRetry && (
      <button onClick={onRetry} className="rounded border border-ss-border bg-ss-panel px-3 py-1 text-[13px] text-ss-text hover:bg-ss-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent">
        Retry
      </button>
    )}
  </div>
);

export const timeAgo = (iso: string, now = Date.now()) => {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }) + ' IST';

export const formatHours = (hours: number) => (hours >= 48 ? `~${Math.round(hours / 24)} days` : `~${Math.max(1, Math.round(hours))} h`);

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/** Focus the dialog on open, trap Tab inside, close on Escape, restore focus on close. */
export function useDialog<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeRef.current();
      } else if (event.key === 'Tab' && node) {
        const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((item) => item.offsetParent !== null);
        if (items.length === 0) return;
        const [head, tail] = [items[0], items[items.length - 1]];
        if (event.shiftKey && document.activeElement === head) {
          event.preventDefault();
          tail.focus();
        } else if (!event.shiftKey && document.activeElement === tail) {
          event.preventDefault();
          head.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
  }, [open]);
  return ref;
}

export const CloseButton = ({ onClick, label = 'Close' }: { onClick: () => void; label?: string }) => (
  <button
    onClick={onClick}
    aria-label={label}
    className="rounded p-1.5 text-ss-textmuted hover:bg-ss-border hover:text-ss-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent"
  >
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  </button>
);

export function ConfirmDialog({ open, title, body, confirmLabel, onConfirm, onCancel }: { open: boolean; title: string; body: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void }) {
  const ref = useDialog<HTMLDivElement>(open, onCancel);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1300] flex items-center justify-center bg-black/60" onMouseDown={onCancel}>
      <div ref={ref} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" className="w-[380px] rounded-lg border border-ss-border bg-ss-panel p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <h2 id="confirm-title" className="text-[15px] font-semibold text-ss-text">{title}</h2>
        <p className="mt-2 text-[13px] leading-relaxed text-ss-textmuted">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded border border-ss-border px-3 py-1.5 text-[13px] text-ss-text hover:bg-ss-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent">Cancel</button>
          <button onClick={onConfirm} className="rounded bg-ss-accent px-3 py-1.5 text-[13px] font-semibold text-ss-bg hover:bg-ss-accent/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

export const SectionTitle = ({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) => (
  <div className="mb-2 flex items-baseline justify-between gap-2">
    <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ss-textmuted">{children}</h3>
    {aside && <div className="text-[12px] text-ss-textmuted">{aside}</div>}
  </div>
);
