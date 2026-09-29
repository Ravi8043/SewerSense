import { useState } from 'react';
import type { FullIncident, Source, Status, Velocity } from '../types';
import { BAND_COLORS, ConfidencePill, ErrorState, SOURCE_META, STATUS_LABELS, SectionTitle, Skeleton, SourceIcon, VelocityBadge, categoryLabel, formatHours, formatTime } from './shared';

interface Props {
  incident: FullIncident | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onViewEvidence: () => void;
  onGenerateBrief: () => void;
  onStatusChange: (status: Status) => Promise<void>;
}

function PriorityRing({ priority, color }: { priority: number; color: string }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  return (
    <svg viewBox="0 0 64 64" className="h-16 w-16 shrink-0" role="img" aria-label={`Priority ${priority} of 100`}>
      <circle cx="32" cy="32" r={radius} fill="none" stroke="#1c2431" strokeWidth="6" />
      <circle cx="32" cy="32" r={radius} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" strokeDasharray={`${(priority / 100) * circumference} ${circumference}`} transform="rotate(-90 32 32)" />
      <text x="32" y="37" textAnchor="middle" fontSize="18" fontWeight="700" fill="#f8fafc">{priority}</text>
    </svg>
  );
}

function SourceMixBar({ mix }: { mix: Partial<Record<Source, number>> }) {
  const entries = (Object.entries(mix) as [Source, number][]).filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0) || 1;
  let offset = 0;
  return (
    <div>
      <svg viewBox="0 0 100 6" preserveAspectRatio="none" className="h-2.5 w-full overflow-hidden rounded" role="img" aria-label="Source mix">
        {entries.map(([source, count]) => {
          const width = (count / total) * 100;
          const rect = <rect key={source} x={offset} y="0" width={Math.max(0, width - 0.4)} height="6" fill={SOURCE_META[source].color} />;
          offset += width;
          return rect;
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {entries.map(([source, count]) => (
          <span key={source} className="flex items-center gap-1 text-[12px] text-ss-textmuted">
            <SourceIcon source={source} />
            {SOURCE_META[source].label} <span className="tabular-nums text-ss-text">{count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function VelocitySparkline({ velocity }: { velocity: Velocity }) {
  const max = Math.max(1, ...velocity.buckets);
  const width = 132;
  const height = 34;
  const barWidth = width / velocity.buckets.length;
  return (
    <svg viewBox={`0 0 ${width} ${height + 12}`} className="h-[46px] w-[132px]" role="img" aria-label={`Hourly reports, last 6 hours: ${velocity.buckets.join(', ')}`}>
      {velocity.buckets.map((count, index) => {
        const barHeight = (count / max) * height;
        const recent = index >= velocity.buckets.length / 2;
        return (
          <g key={index}>
            <rect x={index * barWidth + 3} y={height - barHeight} width={barWidth - 6} height={Math.max(1, barHeight)} rx="1.5" fill={recent ? '#22d3ee' : '#334155'} />
            {count > 0 && (
              <text x={index * barWidth + barWidth / 2} y={height - barHeight - 2} textAnchor="middle" fontSize="8" fill="#94a3b8">{count}</text>
            )}
          </g>
        );
      })}
      <text x="0" y={height + 11} fontSize="8" fill="#64748b">-6h</text>
      <text x={width} y={height + 11} fontSize="8" fill="#64748b" textAnchor="end">latest</text>
    </svg>
  );
}

const Stat = ({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) => (
  <div className="rounded border border-ss-border bg-ss-bg px-3 py-2">
    <div className="text-[11px] uppercase tracking-[0.06em] text-ss-textmuted">{label}</div>
    <div className="mt-0.5 text-[17px] font-semibold tabular-nums text-ss-text">{value}</div>
    {note && <div className="text-[11px] text-ss-textmuted">{note}</div>}
  </div>
);

const STATUS_ORDER: Status[] = ['open', 'verified', 'dispatched', 'resolved'];

function StatusControl({ status, onChange }: { status: Status; onChange: (status: Status) => Promise<void> }) {
  const [pending, setPending] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const change = async (next: Status) => {
    if (next === status || pending) return;
    setPending(next);
    setError(null);
    try {
      await onChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Status update failed');
    } finally {
      setPending(null);
    }
  };
  return (
    <div>
      <div className="flex rounded border border-ss-border p-0.5" role="radiogroup" aria-label="Incident status">
        {STATUS_ORDER.map((item) => (
          <button
            key={item}
            role="radio"
            aria-checked={status === item}
            disabled={pending !== null}
            onClick={() => change(item)}
            className={`flex-1 rounded px-2 py-1 text-[12px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent ${
              status === item ? 'bg-ss-accent/15 text-ss-accent' : 'text-ss-textmuted hover:bg-ss-border hover:text-ss-text'
            } ${pending === item ? 'animate-pulse' : ''}`}
          >
            {STATUS_LABELS[item]}
          </button>
        ))}
      </div>
      {error && <div role="alert" className="mt-1 text-[12px] text-red-300">Could not update status: {error}</div>}
    </div>
  );
}

export function IncidentCard({ incident, loading, error, onRetry, onViewEvidence, onGenerateBrief, onStatusChange }: Props) {
  if (error && !incident) {
    return (
      <aside className="flex min-h-0 flex-col border-l border-ss-border bg-ss-panel">
        <ErrorState message={`Could not load incident: ${error}`} onRetry={onRetry} />
      </aside>
    );
  }
  if (!incident) {
    return (
      <aside className="flex min-h-0 flex-col gap-4 border-l border-ss-border bg-ss-panel p-5" aria-busy={loading}>
        {loading ? (
          <>
            <div className="flex gap-3">
              <Skeleton className="h-16 w-16 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-5 w-4/5" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
            <Skeleton className="h-24" />
            <Skeleton className="h-32" />
          </>
        ) : (
          <div className="m-auto text-center text-[13px] text-ss-textmuted">Select an incident from the queue or map.</div>
        )}
      </aside>
    );
  }

  const color = BAND_COLORS[incident.band];
  const topFactors = incident.priority_factors.filter((factor) => factor.contribution > 0).slice(0, 4);
  const extent = incident.corridor ? `~${Math.round(incident.corridor.length_m)} m` : `~${Math.round(incident.radius_m)} m radius`;

  return (
    <aside className={`flex min-h-0 flex-col border-l border-ss-border bg-ss-panel ${loading ? 'opacity-70' : ''} transition-opacity`} aria-label="Selected incident" aria-busy={loading}>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-ss-border p-4">
          <div className="flex gap-3">
            <PriorityRing priority={incident.priority} color={color} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]">
                <span className="font-bold tracking-wide" style={{ color }}>{incident.band}</span>
                <span className="text-ss-textmuted">{incident.id}</span>
                <VelocityBadge label={incident.velocity_label} />
              </div>
              <h2 className="mt-0.5 text-[16px] font-semibold leading-snug text-ss-text">{incident.title}</h2>
              <div className="text-[12px] text-ss-textmuted">
                {categoryLabel(incident.category)} · first reported {formatTime(incident.first_reported)}
              </div>
            </div>
          </div>
          {incident.severity_floor_applied && (
            <div className="mt-3 rounded border border-orange-400/40 bg-orange-400/10 px-3 py-2 text-[12px] text-orange-200">
              Severity floor applied: a severe hazard near a sensitive place lifts priority from {incident.base_priority} to {incident.priority}, even with few reports.
            </div>
          )}
          <div className="mt-3">
            <StatusControl status={incident.status} onChange={onStatusChange} />
          </div>
        </div>

        <div className="space-y-5 p-4">
          <div>
            <SectionTitle aside="reported">Signals</SectionTitle>
            <div className="grid grid-cols-3 gap-2">
              <Stat label="Reports" value={incident.report_count} note={incident.duplicate_count ? `${incident.duplicate_count} duplicates counted once` : 'no duplicates'} />
              <Stat label="Independent" value={incident.unique_sources} note="distinct sources" />
              <Stat label="Unresolved" value={formatHours(incident.duration_hours)} note="from report times" />
            </div>
          </div>

          <div>
            <SectionTitle aside="estimated by SewerSense">Impact</SectionTitle>
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Households" value={<>~{incident.est_households} <span className="text-[12px] font-normal text-ss-textmuted">est.</span></>} note="not confirmed" />
              <Stat label={incident.corridor ? 'Affected stretch' : 'Affected area'} value={<>{extent} <span className="text-[12px] font-normal text-ss-textmuted">est.</span></>} note={incident.corridor ? `${incident.corridor.confidence.points} located reports` : 'no linear pattern'} />
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {incident.road_blocked && <span className="rounded border border-red-400/40 bg-red-400/10 px-2 py-0.5 text-[12px] text-red-200">Road blocked (reported)</span>}
              {incident.health_risk && <span className="rounded border border-orange-400/40 bg-orange-400/10 px-2 py-0.5 text-[12px] text-orange-200">Health risk (reported)</span>}
              {incident.sensitive_place && <span className="rounded border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[12px] text-amber-200">Near {incident.sensitive_place}</span>}
            </div>
          </div>

          <div>
            <SectionTitle aside={`${incident.unique_sources} independent`}>Source mix</SectionTitle>
            <SourceMixBar mix={incident.source_mix} />
          </div>

          <div className="flex items-center justify-between rounded border border-ss-border bg-ss-bg px-3 py-2">
            <div>
              <div className="text-[11px] uppercase tracking-[0.06em] text-ss-textmuted">Velocity · hourly reports</div>
              <div className="mt-1"><VelocityBadge label={incident.velocity_label} /></div>
              <div className="mt-0.5 text-[12px] text-ss-textmuted">
                {incident.velocity.recent} in latest 3 h vs {incident.velocity.prior} before
              </div>
            </div>
            <VelocitySparkline velocity={incident.velocity} />
          </div>

          <div>
            <SectionTitle aside={<ConfidencePill label={incident.confidence_label} />}>Confidence</SectionTitle>
            <ul className="space-y-0.5 text-[12px] text-ss-textmuted">
              {incident.confidence_reasons.map((reason) => (
                <li key={reason}>· {reason}</li>
              ))}
            </ul>
          </div>

          <div>
            <SectionTitle aside="points of 100">Why {incident.band.toLowerCase()}?</SectionTitle>
            <ol className="space-y-2">
              {topFactors.map((factor) => (
                <li key={factor.name} className="flex gap-3 text-[13px]">
                  <span className="w-10 shrink-0 text-right font-semibold tabular-nums text-ss-accent">+{factor.contribution.toFixed(0)}</span>
                  <span>
                    <span className="font-medium text-ss-text">{factor.name}.</span> <span className="text-ss-textmuted">{factor.sentence}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>

      <div className="grid shrink-0 grid-cols-2 gap-2 border-t border-ss-border bg-ss-bg p-3">
        <button onClick={onViewEvidence} className="rounded border border-ss-border px-3 py-2 text-[13px] font-medium text-ss-text hover:bg-ss-panel focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent">
          View evidence
        </button>
        <button onClick={onGenerateBrief} className="rounded bg-ss-accent px-3 py-2 text-[13px] font-semibold text-ss-bg hover:bg-ss-accent/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">
          Generate response brief
        </button>
      </div>
    </aside>
  );
}
