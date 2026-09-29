import { useEffect, useRef, useState } from 'react';
import type { SimulateResponse } from '../types';

const STAGE_NAMES = ['Reports received', 'Classifying', 'Extracting locations', 'Finding duplicates', 'Clustering incidents', 'Calculating priority'];
const MIN_STAGE_MS = 600;
const RESULT_HOLD_MS = 2600;

interface Props {
  result: SimulateResponse | null; // null while the request is in flight
  onDone: () => void;
}

function stageDetail(name: string, count: number, result: SimulateResponse) {
  switch (name) {
    case 'Reports received':
      return `${count} raw complaints`;
    case 'Classifying':
      return `${count} sewerage · ${result.out_of_scope} out of scope`;
    case 'Extracting locations':
      return `${count} located · ${result.unlocated} unlocated`;
    case 'Finding duplicates':
      return `${count} repeat posts counted once`;
    case 'Clustering incidents':
      return `${count} incidents (${result.new_incident_ids.length} new)`;
    default:
      return `${count} incidents re-scored`;
  }
}

export function SimulationOverlay({ result, onDone }: Props) {
  const [active, setActive] = useState(0);
  const [showResult, setShowResult] = useState(false);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];
    let elapsed = 0;
    result.stages.forEach((stage, index) => {
      timers.push(setTimeout(() => !cancelled && setActive(index), elapsed));
      elapsed += Math.max(MIN_STAGE_MS, stage.ms);
    });
    timers.push(setTimeout(() => !cancelled && setShowResult(true), elapsed));
    timers.push(setTimeout(() => !cancelled && doneRef.current(), elapsed + RESULT_HOLD_MS));
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [result]);

  const stages = result?.stages ?? STAGE_NAMES.map((name) => ({ name, count: 0, ms: 0 }));

  return (
    <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-ss-bg/80 backdrop-blur-[2px]" role="status" aria-live="polite">
      {!showResult || !result ? (
        <div className="w-[420px] rounded-lg border border-ss-border bg-ss-panel p-5 shadow-2xl">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="text-[15px] font-semibold text-ss-text">Processing incoming complaints</h2>
            <span className="text-[12px] text-ss-textmuted">{result ? `stage ${active + 1} of ${stages.length}` : 'sending batch…'}</span>
          </div>
          <ol className="space-y-1">
            {stages.map((stage, index) => {
              const state = !result ? (index === 0 ? 'active' : 'pending') : index < active ? 'done' : index === active ? 'active' : 'pending';
              return (
                <li key={stage.name} className={`flex items-center justify-between rounded px-2 py-1.5 transition-colors ${state === 'active' ? 'bg-ss-accent/10' : ''}`}>
                  <span className="flex items-center gap-2.5">
                    <span className="flex h-4 w-4 items-center justify-center" aria-hidden="true">
                      {state === 'done' ? (
                        <svg viewBox="0 0 16 16" className="h-4 w-4 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2.2}><path d="m3.5 8.5 3 3 6-7" /></svg>
                      ) : state === 'active' ? (
                        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-ss-accent" />
                      ) : (
                        <span className="h-2 w-2 rounded-full bg-ss-border" />
                      )}
                    </span>
                    <span className={`text-[13px] ${state === 'active' ? 'font-semibold text-ss-accent' : state === 'done' ? 'text-ss-text' : 'text-ss-textmuted'}`}>{stage.name}</span>
                  </span>
                  <span className="text-right text-[12px] tabular-nums text-ss-textmuted">
                    {result && state !== 'pending' ? stageDetail(stage.name, stage.count, result) : ''}
                    {result && state === 'done' && <span className="ml-2 opacity-60">{stage.ms} ms</span>}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      ) : (
        <button onClick={() => doneRef.current()} className="animate-pop flex flex-col items-center rounded-xl px-10 py-8 text-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent" aria-label="Continue to the map">
          <div className="text-[52px] font-extrabold leading-none tracking-tight text-white">
            {result.received} <span className="text-[28px] font-semibold text-ss-textmuted">REPORTS</span>
          </div>
          <div className="my-2 text-[28px] text-ss-accent" aria-hidden="true">↓</div>
          <div className="text-[52px] font-extrabold leading-none tracking-tight text-ss-accent">
            {result.batch_incident_count} <span className="text-[28px] font-semibold">INCIDENTS</span>
          </div>
          <div className="mt-4 rounded-full border border-ss-border bg-ss-panel px-4 py-1.5 text-[12px] text-ss-textmuted">
            {result.new_incident_ids.length} new · {result.updated_incident_ids.length} updated · {result.duplicates} duplicates · {result.out_of_scope} out of scope · {result.elapsed_ms} ms server time
          </div>
          <div className="mt-3 text-[12px] text-ss-textmuted">Click to continue</div>
        </button>
      )}
    </div>
  );
}
