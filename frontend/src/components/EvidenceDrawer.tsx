import type { EvidenceResponse } from '../types';
import { CloseButton, ErrorState, GEO_LABELS, SOURCE_META, SectionTitle, Skeleton, SourceIcon, formatTime, useDialog } from './shared';

interface Props {
  open: boolean;
  incidentId: string | null;
  incidentTitle: string;
  evidence: EvidenceResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
}

const SCORE_PARTS = [
  { key: 'semantic', label: 'Content', weight: 0.3 },
  { key: 'geographic', label: 'Proximity', weight: 0.35 },
  { key: 'temporal', label: 'Recency', weight: 0.15 },
  { key: 'category', label: 'Category', weight: 0.2 },
] as const;

export function EvidenceDrawer({ open, incidentId, incidentTitle, evidence, loading, error, onRetry, onClose }: Props) {
  const ref = useDialog<HTMLDivElement>(open, onClose);
  if (!open) return null;
  const data = evidence && evidence.incident_id === incidentId ? evidence : null;

  return (
    <>
      <div className="fixed inset-0 z-[1100] bg-black/40" onClick={onClose} aria-hidden="true" />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="evidence-title" className="animate-slide-in fixed right-0 top-0 z-[1101] flex h-full w-[500px] max-w-full flex-col border-l border-ss-border bg-ss-panel shadow-2xl">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-ss-border p-4">
          <div className="min-w-0">
            <h2 id="evidence-title" className="text-[16px] font-semibold text-ss-text">Evidence &amp; audit trail</h2>
            <div className="truncate text-[12px] text-ss-textmuted">{incidentId} · {incidentTitle}</div>
          </div>
          <CloseButton onClick={onClose} label="Close evidence" />
        </div>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-4">
          {error && !data ? (
            <ErrorState message={`Could not load evidence: ${error}`} onRetry={onRetry} />
          ) : loading || !data ? (
            <div className="space-y-3">
              <Skeleton className="h-5 w-1/3" />
              {Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-8 w-full" />)}
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : (
            <>
              <section>
                <SectionTitle aside={<>total <span className="font-semibold tabular-nums text-ss-text">{data.priority}</span>/100</>}>Priority breakdown</SectionTitle>
                <div className="space-y-2.5">
                  {data.factors.map((factor) => (
                    <div key={factor.name}>
                      <div className="flex items-baseline justify-between text-[13px]">
                        <span className="text-ss-text">{factor.name}</span>
                        <span className="tabular-nums text-ss-textmuted">
                          <span className="font-semibold text-ss-accent">{factor.contribution.toFixed(1)}</span> / {(factor.weight * 100).toFixed(0)}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 w-full rounded-full bg-ss-bg" aria-hidden="true">
                        <div className="h-1.5 rounded-full bg-ss-accent" style={{ width: `${factor.value * 100}%` }} />
                      </div>
                      <div className="mt-0.5 text-[12px] text-ss-textmuted">{factor.sentence}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 rounded border border-ss-border bg-ss-bg px-3 py-2 text-[12px] text-ss-textmuted">
                  Sum of contributions: <span className="font-semibold text-ss-text">{data.base_priority}</span>
                  {data.severity_floor_applied ? (
                    <> → raised to <span className="font-semibold text-orange-300">{data.priority}</span> by the severity floor (severe hazard near a school, hospital or market).</>
                  ) : (
                    <> = priority {data.priority}.</>
                  )}
                </div>
              </section>

              <section>
                <SectionTitle aside={`${data.cluster_summary.reports_scored} grouping decisions`}>Why these reports were grouped</SectionTitle>
                {data.cluster_summary.reports_scored > 0 && (
                  <div className="mb-2 grid grid-cols-4 gap-2">
                    {SCORE_PARTS.map((part) => (
                      <div key={part.key} className="rounded border border-ss-border bg-ss-bg px-2 py-1.5">
                        <div className="text-[11px] text-ss-textmuted">{part.label} ×{part.weight}</div>
                        <div className="text-[15px] font-semibold tabular-nums text-ss-text">{data.cluster_summary[part.key].toFixed(2)}</div>
                      </div>
                    ))}
                  </div>
                )}
                <ul className="space-y-1 text-[12px] text-ss-textmuted">
                  {data.cluster_summary.reasons.map((reason) => (
                    <li key={reason}>· {reason}</li>
                  ))}
                </ul>
              </section>

              <section>
                <SectionTitle
                  aside={
                    <span className={`rounded border px-1.5 py-px text-[11px] ${data.extraction.hybrid_validated ? 'border-emerald-400/40 text-emerald-300' : 'border-amber-400/40 text-amber-300'}`}>
                      {data.extraction.label} · location confidence {Math.round(data.extraction.location_confidence * 100)}%
                    </span>
                  }
                >
                  Representative reports
                </SectionTitle>
                <div className="mb-2 text-[12px] text-ss-textmuted">
                  Showing {data.representative_reports.length} of {data.total_reports} reports
                  {data.duplicate_count > 0 && <> · {data.duplicate_count} duplicates kept as evidence but counted once</>}.
                </div>
                <ul className="space-y-2">
                  {data.representative_reports.map((report) => (
                    <li key={report.id} className={`rounded border p-3 ${report.is_duplicate ? 'border-dashed border-ss-border/70 bg-transparent opacity-60' : 'border-ss-border bg-ss-bg'}`}>
                      <div className="mb-1.5 flex items-center justify-between gap-2 text-[12px]">
                        <span className="flex min-w-0 items-center gap-1.5">
                          <SourceIcon source={report.source} />
                          <span className="font-medium" style={{ color: SOURCE_META[report.source].color }}>{SOURCE_META[report.source].label}</span>
                          <span className="truncate text-ss-textmuted">{report.source_handle}</span>
                        </span>
                        <span className="shrink-0 text-ss-textmuted">{formatTime(report.created_at)}</span>
                      </div>
                      <p className="text-[13px] leading-snug text-ss-text">“{report.raw_text}”</p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
                        <span className="rounded border border-ss-border px-1.5 py-px text-ss-textmuted">{GEO_LABELS[report.geo_quality]}</span>
                        {report.is_duplicate ? (
                          <span className="rounded border border-ss-border px-1.5 py-px font-semibold text-ss-textmuted">Duplicate · counted once</span>
                        ) : report.cluster_score !== null ? (
                          <span className="rounded border border-ss-accent/40 px-1.5 py-px text-ss-accent">Grouping score {report.cluster_score.toFixed(2)}</span>
                        ) : (
                          <span className="rounded border border-ss-border px-1.5 py-px text-ss-textmuted">First report</span>
                        )}
                        {report.extraction_mode && <span className="text-ss-textmuted">{report.extraction_mode === 'hybrid_validated' ? 'hybrid validated' : 'rules fallback'}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
}
