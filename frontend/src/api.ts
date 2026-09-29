// The only HTTP boundary in the frontend.
import type {
  BriefResponse,
  Dataset,
  IngestResponse,
  LiveSource,
  CompactIncident,
  EvidenceResponse,
  FullIncident,
  HealthResponse,
  HeatmapPoint,
  ResetResponse,
  SimulateResponse,
  Status,
  StatusResponse,
  Summary,
} from './types';

const BASE_URL = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

// Which dataset every read/write targets. Demo is the default and the only one simulation uses.
let currentDataset: Dataset = 'demo';
export const setDataset = (dataset: Dataset) => {
  currentDataset = dataset;
};
export const getDataset = () => currentDataset;

const withDataset = (path: string) => (currentDataset === 'demo' ? path : `${path}${path.includes('?') ? '&' : '?'}dataset=${currentDataset}`);

export const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${withDataset(path)}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError('Cannot reach the SewerSense API. Is the backend running?', 0);
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail.map((item: { msg?: string }) => item.msg).join('; ');
    } catch {
      // A non-JSON 5xx comes from the dev proxy or a gateway, not from FastAPI.
      if (response.status >= 500) detail = `SewerSense API unavailable (HTTP ${response.status}). Is the backend running?`;
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>('/health', { signal }),
  summary: (signal?: AbortSignal) => request<Summary>('/summary', { signal }),
  incidents: (params: { status?: Status | 'active'; min_priority?: number } = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.min_priority !== undefined) query.set('min_priority', String(params.min_priority));
    const suffix = query.toString() ? `?${query}` : '';
    return request<CompactIncident[]>(`/incidents${suffix}`, { signal });
  },
  incident: (id: string, signal?: AbortSignal) => request<FullIncident>(`/incidents/${encodeURIComponent(id)}`, { signal }),
  evidence: (id: string, signal?: AbortSignal) => request<EvidenceResponse>(`/incidents/${encodeURIComponent(id)}/evidence`, { signal }),
  heatmap: (signal?: AbortSignal) => request<HeatmapPoint[]>('/heatmap', { signal }),
  simulate: () => request<SimulateResponse>('/simulate', { method: 'POST' }),
  brief: (id: string, signal?: AbortSignal) => request<BriefResponse>(`/incidents/${encodeURIComponent(id)}/brief`, { method: 'POST', signal }),
  setStatus: (id: string, status: Status) =>
    request<StatusResponse>(`/incidents/${encodeURIComponent(id)}/status`, { method: 'POST', body: JSON.stringify({ status }) }),
  reset: () => request<ResetResponse>('/reset', { method: 'POST' }),
  ingest: (sources: LiveSource[]) => request<IngestResponse>('/ingest', { method: 'POST', body: JSON.stringify({ sources }) }),
};
