import { useState } from 'react';
import type { BriefResponse } from '../types';
import { CloseButton, ErrorState, Skeleton, useDialog } from './shared';

interface Props {
  open: boolean;
  incidentId: string | null;
  incidentTitle: string;
  brief: BriefResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
}

export function BriefModal({ open, incidentId, incidentTitle, brief, loading, error, onRetry, onClose }: Props) {
  const ref = useDialog<HTMLDivElement>(open, onClose);
  const [copied, setCopied] = useState(false);
  if (!open) return null;

  const copy = async () => {
    if (!brief) return;
    const text = [
      `SewerSense response brief — ${incidentId} ${incidentTitle}`,
      '',
      'REPORTED FACTS',
      ...brief.facts.map((line) => `- ${line}`),
      '',
      'AI ASSESSMENT (estimates, verify before action)',
      ...brief.assessment.map((line) => `- ${line}`),
      '',
      brief.recommended_next_step,
      '',
      'AI-generated from synthetic demo data. Verify before action.',
    ].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/60 p-4" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="brief-title" className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-lg border border-ss-border bg-ss-bg shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 rounded-t-lg border-b border-ss-border bg-ss-panel p-4">
          <div className="min-w-0">
            <h2 id="brief-title" className="text-[16px] font-semibold text-ss-text">Response brief</h2>
            <div className="truncate text-[12px] text-ss-textmuted">{incidentId} · {incidentTitle}</div>
          </div>
          <div className="flex items-center gap-2">
            {brief && (
              <span className={`rounded border px-2 py-0.5 text-[11px] font-medium ${brief.generated_by === 'llm' ? 'border-violet-400/40 text-violet-300' : 'border-ss-border text-ss-textmuted'}`}>
                {brief.generated_by === 'llm' ? 'LLM · validated' : 'Template'}
              </span>
            )}
            <CloseButton onClick={onClose} label="Close brief" />
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5" aria-busy={loading}>
          {error && !brief ? (
            <ErrorState message={`Could not generate the brief: ${error}`} onRetry={onRetry} />
          ) : loading || !brief ? (
            <div className="space-y-5">
              {[3, 4].map((lines, block) => (
                <div key={block} className="space-y-2">
                  <Skeleton className="h-4 w-1/3" />
                  {Array.from({ length: lines }, (_, index) => <Skeleton key={index} className={`h-3.5 ${index % 2 ? 'w-5/6' : 'w-full'}`} />)}
                </div>
              ))}
            </div>
          ) : (
            <>
              <section className="rounded border border-sky-400/30 bg-sky-400/5 p-4">
                <h3 className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-sky-300">
                  Reported facts <span className="font-normal normal-case tracking-normal text-ss-textmuted">— what the reports and counts say</span>
                </h3>
                <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-ss-text">
                  {brief.facts.map((line) => <li key={line}>{line}</li>)}
                </ul>
              </section>
              <section className="rounded border border-amber-400/30 bg-amber-400/5 p-4">
                <h3 className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-amber-300">
                  AI assessment <span className="font-normal normal-case tracking-normal text-ss-textmuted">— estimates and interpretation, not confirmed</span>
                </h3>
                <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-ss-text">
                  {brief.assessment.map((line) => <li key={line}>{line}</li>)}
                </ul>
              </section>
              <section className="rounded border border-ss-accent/40 bg-ss-accent/5 p-4">
                <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.08em] text-ss-accent">Recommended next step</h3>
                <p className="text-[13px] text-ss-text">{brief.recommended_next_step}</p>
              </section>
            </>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 rounded-b-lg border-t border-ss-border bg-ss-panel px-4 py-3">
          <div className="flex items-center gap-2 text-[12px] font-medium text-amber-200">
            <span className="h-2 w-2 rounded-full bg-amber-400" aria-hidden="true" />
            AI-generated. Verify before action.
          </div>
          <button
            onClick={copy}
            disabled={!brief || loading}
            className="rounded border border-ss-border px-3 py-1.5 text-[13px] text-ss-text hover:bg-ss-border disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent"
          >
            {copied ? 'Copied ✓' : 'Copy brief'}
          </button>
        </div>
      </div>
    </div>
  );
}
