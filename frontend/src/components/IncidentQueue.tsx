import { useEffect, useRef } from 'react';
import type { CompactIncident } from '../types';
import { BAND_COLORS, ErrorState, PriorityBadge, Skeleton, StatusPill, VelocityBadge, categoryLabel, timeAgo } from './shared';

export type QueueFilter = 'active' | 'critical' | 'all' | 'resolved';

const FILTERS: { key: QueueFilter; label: string }[] = [
  { key: 'active', label: 'Active' },
  { key: 'critical', label: 'Critical' },
  { key: 'all', label: 'All' },
  { key: 'resolved', label: 'Resolved' },
];

export const applyQueueFilter = (incidents: CompactIncident[], filter: QueueFilter) =>
  incidents.filter((item) =>
    filter === 'all' ? true : filter === 'resolved' ? item.status === 'resolved' : filter === 'critical' ? item.status !== 'resolved' && item.band === 'CRITICAL' : item.status !== 'resolved',
  );

interface Props {
  incidents: CompactIncident[];
  totalLoaded: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  filter: QueueFilter;
  onFilter: (filter: QueueFilter) => void;
  counts: Record<QueueFilter, number>;
  newIds: Set<string>;
  updatedIds: Set<string>;
  emptyMessage?: string;
}

export function IncidentQueue({ incidents, totalLoaded, selectedId, onSelect, loading, error, onRetry, filter, onFilter, counts, newIds, updatedIds, emptyMessage }: Props) {
  const selectedRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [selectedId]);

  return (
    <section className="flex min-h-0 flex-col border-r border-ss-border bg-ss-bg" aria-label="Incident queue">
      <div className="shrink-0 border-b border-ss-border bg-ss-panel px-3 pb-2 pt-2.5">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ss-textmuted">Incident queue</h2>
          <span className="text-[12px] text-ss-textmuted">by priority</span>
        </div>
        <div className="flex gap-1" role="tablist" aria-label="Filter incidents">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              role="tab"
              aria-selected={filter === item.key}
              onClick={() => onFilter(item.key)}
              className={`rounded px-2 py-1 text-[12px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent ${
                filter === item.key ? 'bg-ss-accent/15 text-ss-accent' : 'text-ss-textmuted hover:bg-ss-border hover:text-ss-text'
              }`}
            >
              {item.label} <span className="tabular-nums opacity-70">{totalLoaded ? counts[item.key] : ''}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error && incidents.length === 0 ? (
          <ErrorState message={`Could not load incidents: ${error}`} onRetry={onRetry} />
        ) : loading && !totalLoaded ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 7 }, (_, index) => (
              <div key={index} className="space-y-2 rounded border border-ss-border p-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        ) : incidents.length === 0 ? (
          <div className="flex h-full items-center justify-center p-6 text-center text-[13px] text-ss-textmuted">
            {emptyMessage ?? 'No incidents match this filter.'}
          </div>
        ) : (
          <ul className="divide-y divide-ss-border/60">
            {incidents.map((incident) => {
              const selected = incident.id === selectedId;
              const isNew = newIds.has(incident.id);
              const isUpdated = !isNew && updatedIds.has(incident.id);
              return (
                <li key={incident.id}>
                  <button
                    ref={selected ? selectedRef : undefined}
                    onClick={() => onSelect(incident.id)}
                    aria-current={selected ? 'true' : undefined}
                    title={`${incident.id} · ${incident.title}`}
                    className={`relative block w-full py-2.5 pl-4 pr-3 text-left transition-colors focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-ss-accent ${
                      selected ? 'bg-ss-panel' : 'hover:bg-ss-panel/60'
                    } ${isNew || isUpdated ? 'animate-flash' : ''}`}
                  >
                    <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: BAND_COLORS[incident.band], opacity: incident.status === 'resolved' ? 0.35 : 1 }} aria-hidden="true" />
                    {selected && <span className="absolute inset-y-0 right-0 w-[2px] bg-ss-accent" aria-hidden="true" />}
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          {isNew && <span className="rounded bg-ss-accent px-1 text-[10px] font-bold uppercase tracking-wide text-ss-bg">New</span>}
                          {isUpdated && <span className="rounded border border-ss-accent/60 px-1 text-[10px] font-bold uppercase tracking-wide text-ss-accent">Updated</span>}
                          <span className={`truncate text-[13px] font-semibold ${incident.status === 'resolved' ? 'text-ss-textmuted' : 'text-ss-text'}`}>
                            {incident.road ?? incident.locality ?? 'Location unconfirmed'}
                          </span>
                        </div>
                        <div className="mt-0.5 truncate text-[12px] text-ss-textmuted">
                          {categoryLabel(incident.category)} · {incident.locality ?? '—'} · {timeAgo(incident.last_reported)}
                        </div>
                      </div>
                      <PriorityBadge band={incident.band} priority={incident.priority} />
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2 text-[12px]">
                      <span className="whitespace-nowrap text-ss-textmuted">
                        <span className="text-ss-text tabular-nums">{incident.report_count}</span> reports ·{' '}
                        <span className="text-ss-text tabular-nums">{incident.unique_sources}</span> sources
                      </span>
                      {incident.status !== 'open' ? <StatusPill status={incident.status} /> : <VelocityBadge label={incident.velocity_label} />}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
