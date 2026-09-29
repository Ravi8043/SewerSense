import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, isAbort } from './api';
import { ArchitectureModal } from './components/ArchitectureModal';
import { BriefModal } from './components/BriefModal';
import { CommandMap } from './components/CommandMap';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { IncidentCard } from './components/IncidentCard';
import { IncidentQueue, applyQueueFilter, type QueueFilter } from './components/IncidentQueue';
import { KpiStrip } from './components/KpiStrip';
import { ConfirmDialog } from './components/shared';
import { SimulationOverlay } from './components/SimulationOverlay';
import { TopBar } from './components/TopBar';
import type { BriefResponse, CompactIncident, EvidenceResponse, FullIncident, HealthResponse, HeatmapPoint, SimulateResponse, Status, Summary } from './types';

const message = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected error');
const FLASH_MS = 9000;
const POLL_MS = 20000;

type Panel<T> = { incidentId: string | null; data: T | null; loading: boolean; error: string | null };
const closedPanel = { incidentId: null, data: null, loading: false, error: null };

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [incidents, setIncidents] = useState<CompactIncident[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapPoint[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [filter, setFilter] = useState<QueueFilter>('active');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<FullIncident | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailNonce, setDetailNonce] = useState(0);

  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<SimulateResponse | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ newIds: Set<string>; updatedIds: Set<string> }>({ newIds: new Set(), updatedIds: new Set() });

  const [evidence, setEvidence] = useState<Panel<EvidenceResponse> & { open: boolean }>({ ...closedPanel, open: false });
  const [brief, setBrief] = useState<Panel<BriefResponse> & { open: boolean }>({ ...closedPanel, open: false });
  const [archOpen, setArchOpen] = useState(false);

  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

  const loadAll = useCallback(async (): Promise<CompactIncident[] | null> => {
    setLoading(true);
    const [summaryResult, incidentResult, heatResult] = await Promise.allSettled([api.summary(), api.incidents(), api.heatmap()]);
    const errors: string[] = [];
    if (summaryResult.status === 'fulfilled') setSummary(summaryResult.value);
    else errors.push(message(summaryResult.reason));
    if (heatResult.status === 'fulfilled') setHeatmap(heatResult.value);
    else errors.push(message(heatResult.reason));
    let list: CompactIncident[] | null = null;
    if (incidentResult.status === 'fulfilled') {
      list = incidentResult.value;
      setIncidents(list);
      setLoaded(true);
      if (!selectedIdRef.current) {
        const first = list.find((item) => item.status !== 'resolved') ?? list[0];
        if (first) setSelectedId(first.id);
      }
    } else errors.push(message(incidentResult.reason));
    setLoadError(errors[0] ?? null);
    setLoading(false);
    return list;
  }, []);

  // Initial load: parallel requests; loadAll selects the highest-priority active incident if none is selected.
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    loadAll();
  }, [loadAll]);

  // Full details for the selection; stale responses are aborted and ignored.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError(null);
    api
      .incident(selectedId, controller.signal)
      .then((data) => {
        if (selectedIdRef.current === data.id) setDetail(data);
      })
      .catch((error) => {
        if (!isAbort(error)) setDetailError(message(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [selectedId, detailNonce]);

  // Quiet background refresh so other operators' changes appear without a reload. The selected
  // card is reloaded only when its compact record actually changed.
  const busyRef = useRef(false);
  busyRef.current = simulating || resetting;
  const incidentsRef = useRef(incidents);
  incidentsRef.current = incidents;
  useEffect(() => {
    const timer = setInterval(async () => {
      if (busyRef.current || document.hidden) return;
      const [summaryResult, incidentResult, heatResult] = await Promise.allSettled([api.summary(), api.incidents(), api.heatmap()]);
      if (busyRef.current) return;
      if (summaryResult.status === 'fulfilled') setSummary(summaryResult.value);
      if (heatResult.status === 'fulfilled') setHeatmap(heatResult.value);
      if (incidentResult.status === 'fulfilled') {
        const fingerprint = (item?: CompactIncident) => (item ? `${item.priority}|${item.report_count}|${item.status}|${item.last_reported}` : '');
        const id = selectedIdRef.current;
        const before = incidentsRef.current.find((item) => item.id === id);
        const after = incidentResult.value.find((item) => item.id === id);
        setIncidents(incidentResult.value);
        if (id && fingerprint(before) !== fingerprint(after)) setDetailNonce((value) => value + 1);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  const select = useCallback((id: string) => setSelectedId(id), []);

  const openEvidence = useCallback(async (retryId?: string) => {
    const incidentId = retryId ?? selectedIdRef.current;
    if (!incidentId) return;
    setEvidence({ open: true, incidentId, data: null, loading: true, error: null });
    try {
      const data = await api.evidence(incidentId);
      setEvidence((current) => (current.incidentId === incidentId ? { ...current, data, loading: false } : current));
    } catch (error) {
      setEvidence((current) => (current.incidentId === incidentId ? { ...current, loading: false, error: message(error) } : current));
    }
  }, []);

  const openBrief = useCallback(async (retryId?: string) => {
    const incidentId = retryId ?? selectedIdRef.current;
    if (!incidentId) return;
    setBrief({ open: true, incidentId, data: null, loading: true, error: null });
    try {
      const data = await api.brief(incidentId);
      setBrief((current) => (current.incidentId === incidentId ? { ...current, data, loading: false } : current));
    } catch (error) {
      setBrief((current) => (current.incidentId === incidentId ? { ...current, loading: false, error: message(error) } : current));
    }
  }, []);

  const changeStatus = useCallback(async (status: Status) => {
    const incidentId = selectedIdRef.current;
    if (!incidentId) return;
    const result = await api.setStatus(incidentId, status); // throws on failure; card shows the error
    setIncidents((list) => list.map((item) => (item.id === result.id ? { ...item, status: result.status } : item)));
    setDetail((current) => (current && current.id === result.id ? { ...current, status: result.status } : current));
    api.summary().then(setSummary).catch(() => undefined);
    api.heatmap().then(setHeatmap).catch(() => undefined);
  }, []);

  const runSimulation = useCallback(async () => {
    setSimError(null);
    setBanner(null);
    setSimResult(null);
    setSimulating(true);
    try {
      setSimResult(await api.simulate());
    } catch (error) {
      setSimulating(false);
      setSimError(message(error));
    }
  }, []);

  const finishSimulation = useCallback(async () => {
    const result = simResult;
    setSimulating(false);
    setSimResult(null);
    if (!result) return;
    await loadAll();
    setFlash({ newIds: new Set(result.new_incident_ids), updatedIds: new Set(result.updated_incident_ids) });
    setFilter('active');
    if (result.hero_incident_id) {
      if (selectedIdRef.current === result.hero_incident_id) setDetailNonce((value) => value + 1);
      setSelectedId(result.hero_incident_id);
    }
    setBanner(`${result.received} reports became ${result.batch_incident_count} incidents (${result.new_incident_ids.length} new, ${result.updated_incident_ids.length} updated).`);
  }, [simResult, loadAll]);

  useEffect(() => {
    if (flash.newIds.size === 0 && flash.updatedIds.size === 0) return;
    const timer = setTimeout(() => setFlash({ newIds: new Set(), updatedIds: new Set() }), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flash]);

  const runReset = useCallback(async () => {
    setConfirmReset(false);
    setResetting(true);
    setSimError(null);
    setBanner(null);
    try {
      const result = await api.reset();
      setSummary(result.summary);
      setEvidence((current) => ({ ...current, open: false }));
      setBrief((current) => ({ ...current, open: false }));
      setFlash({ newIds: new Set(), updatedIds: new Set() });
      setFilter('active');
      await loadAll();
      setDetail(null);
      setSelectedId(result.default_incident_id);
      setDetailNonce((value) => value + 1);
      setBanner('Demo reset to the baseline data.');
    } catch (error) {
      setSimError(`Reset failed: ${message(error)}`);
    } finally {
      setResetting(false);
    }
  }, [loadAll]);

  const counts = useMemo(
    () => ({
      active: applyQueueFilter(incidents, 'active').length,
      critical: applyQueueFilter(incidents, 'critical').length,
      all: incidents.length,
      resolved: applyQueueFilter(incidents, 'resolved').length,
    }),
    [incidents],
  );
  const queue = useMemo(() => applyQueueFilter(incidents, filter), [incidents, filter]);
  const selectedDetail = detail && detail.id === selectedId ? detail : null;
  const selectedTitle = (id: string | null) => incidents.find((item) => item.id === id)?.title ?? '';

  return (
    <div className="flex h-screen w-screen min-w-[1180px] flex-col overflow-hidden">
      <TopBar
        onSimulate={runSimulation}
        onReset={() => setConfirmReset(true)}
        onArchitecture={() => setArchOpen(true)}
        busy={simulating || resetting}
        simulating={simulating}
        health={health}
      />
      <KpiStrip summary={summary} loading={loading} error={loadError} onRetry={loadAll} />

      {(simError || banner || (loadError && loaded)) && (
        <div
          role={simError || loadError ? 'alert' : 'status'}
          className={`flex shrink-0 items-center justify-between gap-3 border-b px-4 py-1.5 text-[13px] ${
            simError || loadError ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-ss-accent/30 bg-ss-accent/10 text-cyan-100'
          }`}
        >
          <span>{simError ? `Simulation failed: ${simError}. The map still shows the previous state.` : loadError && loaded ? `Some data could not be refreshed: ${loadError}` : banner}</span>
          <span className="flex gap-2">
            {simError && (
              <button onClick={runSimulation} className="rounded border border-red-300/40 px-2 py-0.5 hover:bg-red-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Retry</button>
            )}
            {loadError && !simError && (
              <button onClick={loadAll} className="rounded border border-red-300/40 px-2 py-0.5 hover:bg-red-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Retry</button>
            )}
            <button onClick={() => { setSimError(null); setBanner(null); }} aria-label="Dismiss" className="px-1 opacity-70 hover:opacity-100">✕</button>
          </span>
        </div>
      )}

      <main className="grid min-h-0 flex-1 grid-cols-[340px_minmax(420px,1fr)_420px] max-[1360px]:grid-cols-[320px_minmax(400px,1fr)_380px]">
        <IncidentQueue
          incidents={queue}
          totalLoaded={loaded}
          selectedId={selectedId}
          onSelect={select}
          loading={loading}
          error={loaded ? null : loadError}
          onRetry={loadAll}
          filter={filter}
          onFilter={setFilter}
          counts={counts}
          newIds={flash.newIds}
          updatedIds={flash.updatedIds}
        />
        <section className="relative min-h-0 min-w-0" aria-label="Map">
          <CommandMap incidents={incidents} selectedId={selectedId} selected={selectedDetail} heatmap={heatmap} onSelect={select}>
            {simulating && <SimulationOverlay result={simResult} onDone={finishSimulation} />}
          </CommandMap>
        </section>
        <IncidentCard
          incident={selectedDetail}
          loading={detailLoading}
          error={detailError}
          onRetry={() => setDetailNonce((value) => value + 1)}
          onViewEvidence={() => openEvidence()}
          onGenerateBrief={() => openBrief()}
          onStatusChange={changeStatus}
        />
      </main>

      <EvidenceDrawer
        open={evidence.open}
        incidentId={evidence.incidentId}
        incidentTitle={selectedTitle(evidence.incidentId)}
        evidence={evidence.data}
        loading={evidence.loading}
        error={evidence.error}
        onRetry={() => evidence.incidentId && openEvidence(evidence.incidentId)}
        onClose={() => setEvidence((current) => ({ ...current, open: false }))}
      />
      <BriefModal
        open={brief.open}
        incidentId={brief.incidentId}
        incidentTitle={selectedTitle(brief.incidentId)}
        brief={brief.data}
        loading={brief.loading}
        error={brief.error}
        onRetry={() => brief.incidentId && openBrief(brief.incidentId)}
        onClose={() => setBrief((current) => ({ ...current, open: false }))}
      />
      <ArchitectureModal open={archOpen} onClose={() => setArchOpen(false)} />
      <ConfirmDialog
        open={confirmReset}
        title="Reset the demo?"
        body="This rebuilds the synthetic baseline (about 300 reports) through the same pipeline and discards simulated batches and status changes."
        confirmLabel="Reset demo"
        onConfirm={runReset}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}
