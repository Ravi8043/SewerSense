import type { HealthResponse } from '../types';

interface Props {
  onSimulate: () => void;
  onReset: () => void;
  onArchitecture: () => void;
  busy: boolean;
  simulating: boolean;
  health: HealthResponse | null;
}

export function TopBar({ onSimulate, onReset, onArchitecture, busy, simulating, health }: Props) {
  const hybrid = health?.llm_configured;
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-ss-border bg-ss-panel px-4">
      <div className="flex min-w-0 items-center gap-3">
        <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0" aria-hidden="true">
          <circle cx="16" cy="16" r="13" fill="none" stroke="#22d3ee" strokeWidth="2" opacity="0.35" />
          <circle cx="16" cy="16" r="7" fill="none" stroke="#22d3ee" strokeWidth="2" />
          <circle cx="16" cy="16" r="2.5" fill="#22d3ee" />
        </svg>
        <div className="flex min-w-0 flex-col leading-tight">
          <div className="flex items-center gap-2">
            <span className="text-[17px] font-bold tracking-tight text-white">
              Sewer<span className="text-ss-accent">Sense</span>
            </span>
            <span className="rounded border border-amber-400/60 bg-amber-400/10 px-1.5 py-px text-[10px] font-bold uppercase tracking-wider text-amber-300" title="All complaints, places and geometry are synthetic and illustrative">
              Demo data
            </span>
          </div>
          <span className="truncate text-[12px] text-ss-textmuted">Complaint intelligence layer for HMWSSB sewerage operations</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {health && (
          <span
            className="hidden items-center gap-1.5 rounded border border-ss-border px-2 py-1 text-[12px] text-ss-textmuted xl:inline-flex"
            title={hybrid ? 'Rules + validated LLM structured extraction' : 'No LLM key configured: deterministic rules extraction (resilience mode)'}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${hybrid ? 'bg-emerald-400' : 'bg-amber-400'}`} aria-hidden="true" />
            Extraction: {hybrid ? 'hybrid (rules + LLM)' : 'rules mode'}
          </span>
        )}
        <button onClick={onArchitecture} className="rounded px-3 py-1.5 text-[13px] text-ss-textmuted hover:bg-ss-border hover:text-ss-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent">
          Architecture
        </button>
        <button
          onClick={onReset}
          disabled={busy}
          className="rounded border border-ss-border bg-ss-bg px-3 py-1.5 text-[13px] text-ss-text hover:bg-ss-border disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent"
        >
          Reset demo
        </button>
        <button
          onClick={onSimulate}
          disabled={busy}
          className="flex items-center gap-2 rounded bg-ss-accent px-4 py-1.5 text-[13px] font-semibold text-ss-bg hover:bg-ss-accent/90 disabled:cursor-not-allowed disabled:bg-ss-border disabled:text-ss-textmuted focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
        >
          {simulating ? (
            <>
              <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.3" />
                <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" fill="none" />
              </svg>
              Processing…
            </>
          ) : (
            'Simulate incoming complaints'
          )}
        </button>
      </div>
    </header>
  );
}
