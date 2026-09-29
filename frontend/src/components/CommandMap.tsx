import L from 'leaflet';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Circle, CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import type { CompactIncident, FullIncident, HeatmapPoint } from '../types';
import { HeatLayer } from './HeatLayer';
import { BAND_COLORS, categoryLabel } from './shared';

const HYDERABAD: [number, number] = [17.43, 78.46];
const DETAIL_ZOOM = 13; // below this, only priority >= 35 or the top 15 are drawn
const TOP_N_WHEN_ZOOMED_OUT = 15;

// CARTO's dark basemap now requires an API key, so the default is Esri's keyless Dark Gray Canvas.
// Override with VITE_TILE_URL / VITE_TILE_ATTRIBUTION (e.g. a keyed CARTO dark_all URL).
const ENV = import.meta.env;
const CUSTOM_TILES = ENV.VITE_TILE_URL as string | undefined;
const BASE_TILES = CUSTOM_TILES ?? 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
const LABEL_TILES = CUSTOM_TILES ? null : 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}';
const ATTRIBUTION =
  ((ENV.VITE_TILE_ATTRIBUTION as string | undefined) ?? 'Basemap &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors') + ' · Incident geometry is illustrative demo data';

interface Props {
  incidents: CompactIncident[];
  selectedId: string | null;
  selected: FullIncident | null;
  heatmap: HeatmapPoint[];
  onSelect: (id: string) => void;
  children?: React.ReactNode; // overlays rendered inside the map area (simulation)
}

const markerRadius = (priority: number) => 5 + (priority / 100) * 9;

function FlyToSelection({ target }: { target: CompactIncident | null }) {
  const map = useMap();
  const lastId = useRef<string | null>(null);
  useEffect(() => {
    if (!target || target.centroid_lat === null || target.centroid_lon === null) return;
    if (lastId.current === target.id) return;
    lastId.current = target.id;
    map.flyTo([target.centroid_lat, target.centroid_lon], Math.max(map.getZoom(), 16), { duration: 1.1 });
  }, [map, target]);
  return null;
}

// Once full details arrive, frame the estimated corridor so the affected stretch is legible.
function FitCorridor({ incident }: { incident: FullIncident | null }) {
  const map = useMap();
  const lastId = useRef<string | null>(null);
  useEffect(() => {
    if (!incident?.corridor || lastId.current === incident.id) return;
    const bounds = L.latLngBounds([incident.corridor.start, incident.corridor.end]);
    const id = incident.id;
    const timer = setTimeout(() => {
      lastId.current = id;
      map.flyToBounds(bounds, { padding: [140, 140], maxZoom: 18, duration: 0.8 });
    }, 1150);
    return () => clearTimeout(timer);
  }, [map, incident]);
  return null;
}

function ZoomWatcher({ onZoom }: { onZoom: (zoom: number) => void }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) });
  useEffect(() => onZoom(map.getZoom()), [map, onZoom]);
  return null;
}

function SizeKeeper() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(container);
    return () => observer.disconnect();
  }, [map]);
  return null;
}

const pulseIcon = (color: string, size: number) =>
  L.divIcon({ className: '', iconSize: [size, size], html: `<span class="ss-pulse" style="--pulse:${color};width:${size}px;height:${size}px"></span>` });

export function CommandMap({ incidents, selectedId, selected, heatmap, onSelect, children }: Props) {
  const wrapper = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [zoom, setZoom] = useState(12);
  const [showRaw, setShowRaw] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [tileErrors, setTileErrors] = useState(0);
  const [tilesLoaded, setTilesLoaded] = useState(0);

  // Leaflet must mount into a container that already has a non-zero size.
  useEffect(() => {
    const node = wrapper.current;
    if (!node) return;
    const check = () => {
      if (node.clientWidth > 0 && node.clientHeight > 0) setReady(true);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const located = useMemo(() => incidents.filter((item) => item.centroid_lat !== null && item.centroid_lon !== null && item.status !== 'resolved'), [incidents]);
  const visible = useMemo(() => {
    if (zoom >= DETAIL_ZOOM) return located;
    const top = new Set(located.slice(0, TOP_N_WHEN_ZOOMED_OUT).map((item) => item.id));
    return located.filter((item) => item.priority >= 35 || top.has(item.id) || item.id === selectedId);
  }, [located, zoom, selectedId]);
  const selectedCompact = useMemo(() => incidents.find((item) => item.id === selectedId) ?? null, [incidents, selectedId]);
  const detail = selected && selected.id === selectedId ? selected : null;
  const tilesFailing = tileErrors >= 4 && tilesLoaded === 0;

  return (
    <div ref={wrapper} className="relative h-full w-full bg-ss-bg">
      {ready && (
        <MapContainer center={HYDERABAD} zoom={12} minZoom={10} maxZoom={18} zoomControl className="h-full w-full">
          <SizeKeeper />
          <ZoomWatcher onZoom={setZoom} />
          <FlyToSelection target={selectedCompact} />
          <FitCorridor incident={detail} />
          <TileLayer
            attribution={ATTRIBUTION}
            url={BASE_TILES}
            maxNativeZoom={16}
            eventHandlers={{ tileerror: () => setTileErrors((count) => count + 1), tileload: () => setTilesLoaded((count) => count + 1) }}
          />
          {LABEL_TILES && <TileLayer url={LABEL_TILES} maxNativeZoom={16} opacity={0.7} />}
          <HeatLayer points={heatmap} visible={showHeat && !showRaw} />

          {showRaw &&
            heatmap.map(([lat, lon], index) => (
              <CircleMarker key={`raw-${index}`} center={[lat, lon]} radius={3} interactive={false} pathOptions={{ color: '#cbd5e1', weight: 0.5, fillColor: '#cbd5e1', fillOpacity: 0.55 }} />
            ))}

          {detail && detail.centroid_lat !== null && detail.centroid_lon !== null && (
            detail.corridor ? (
              <>
                <Polyline positions={[detail.corridor.start, detail.corridor.end]} pathOptions={{ color: BAND_COLORS[detail.band], weight: 18, opacity: 0.22, lineCap: 'round' }} interactive={false} />
                <Polyline positions={[detail.corridor.start, detail.corridor.end]} pathOptions={{ color: '#fef3c7', weight: 4, opacity: 0.95, lineCap: 'round', className: 'ss-corridor' }}>
                  <Tooltip permanent direction="top" offset={[0, -10]} className="ss-map-label">
                    ~{Math.round(detail.corridor.length_m)} m est. affected stretch
                  </Tooltip>
                </Polyline>
              </>
            ) : (
              <Circle center={[detail.centroid_lat, detail.centroid_lon]} radius={detail.radius_m} interactive={false} pathOptions={{ color: BAND_COLORS[detail.band], weight: 1.5, dashArray: '4 4', fillOpacity: 0.12 }} />
            )
          )}

          {!showRaw &&
            visible
              .filter((item) => item.band === 'CRITICAL' || item.velocity_label === 'RAPIDLY ESCALATING')
              .map((item) => (
                <Marker key={`pulse-${item.id}`} position={[item.centroid_lat!, item.centroid_lon!]} icon={pulseIcon(BAND_COLORS[item.band], markerRadius(item.priority) * 4)} interactive={false} keyboard={false} />
              ))}

          {visible.map((item) => {
            const isSelected = item.id === selectedId;
            return (
              <CircleMarker
                key={`${item.id}-${isSelected}`}
                center={[item.centroid_lat!, item.centroid_lon!]}
                radius={isSelected && detail?.corridor ? 7 : markerRadius(item.priority) * (isSelected ? 1.3 : 1)}
                pathOptions={{ color: isSelected ? '#ffffff' : '#0b0f14', weight: isSelected ? 2.5 : 1, fillColor: BAND_COLORS[item.band], fillOpacity: showRaw ? 0.35 : 0.9 }}
                eventHandlers={{ click: () => onSelect(item.id) }}
              >
                <Tooltip direction="top" offset={[0, -6]}>
                  <div className="text-[12px]">
                    <div className="font-semibold">{item.road ?? item.locality}</div>
                    <div>
                      {categoryLabel(item.category)} · priority {item.priority} ({item.band.toLowerCase()})
                    </div>
                    <div>
                      {item.report_count} reports · {item.unique_sources} sources
                    </div>
                  </div>
                </Tooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>
      )}

      {/* Map controls */}
      <div className="absolute right-3 top-3 z-[500] flex flex-col items-end gap-2">
        <div className="flex overflow-hidden rounded border border-ss-border bg-ss-panel/95 text-[12px] shadow-lg">
          <button
            onClick={() => setShowRaw((value) => !value)}
            aria-pressed={showRaw}
            className={`px-3 py-1.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent ${showRaw ? 'bg-ss-accent/20 text-ss-accent' : 'text-ss-text hover:bg-ss-border'}`}
          >
            {showRaw ? 'Hide raw reports' : 'Show raw reports'}
          </button>
          <button
            onClick={() => setShowHeat((value) => !value)}
            aria-pressed={showHeat}
            disabled={showRaw}
            className={`border-l border-ss-border px-3 py-1.5 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ss-accent ${showHeat ? 'text-ss-text' : 'text-ss-textmuted'} hover:bg-ss-border`}
          >
            Heat {showHeat ? 'on' : 'off'}
          </button>
        </div>
        {showRaw && (
          <div className="max-w-[270px] rounded border border-ss-border bg-ss-panel/95 px-3 py-2 text-[12px] leading-snug text-ss-textmuted shadow-lg">
            <span className="font-semibold text-ss-text">{heatmap.length} raw signals</span> (each dot is one complaint) versus{' '}
            <span className="font-semibold text-ss-text">{located.length} incidents</span>. This clutter is what SewerSense turns into a queue.
          </div>
        )}
        {tilesFailing && (
          <div role="status" className="max-w-[260px] rounded border border-amber-400/40 bg-ss-panel/95 px-3 py-2 text-[12px] text-amber-200 shadow-lg">
            Basemap tiles are unavailable (offline?). Incident data is still shown.
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="absolute bottom-6 left-3 z-[500] w-[228px] rounded border border-ss-border bg-ss-panel/95 p-3 text-[12px] shadow-lg">
        <div className="mb-1.5 font-semibold text-ss-text">Legend</div>
        <div className="mb-2 flex items-center gap-2 text-ss-textmuted">
          <span className="h-3 w-10 rounded-sm" style={{ background: 'linear-gradient(90deg, rgba(34,211,238,.3), #facc15, #ef4444)' }} aria-hidden="true" />
          Heat = report density
        </div>
        <div className="mb-1 text-ss-textmuted">Marker = incident priority (size &amp; colour)</div>
        <div className="mb-2 grid grid-cols-2 gap-x-2 gap-y-1">
          {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((band) => (
            <span key={band} className="flex items-center gap-1.5 text-ss-textmuted">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: BAND_COLORS[band] }} aria-hidden="true" />
              {band.charAt(0) + band.slice(1).toLowerCase()}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2 text-ss-textmuted">
          <span className="h-1 w-10 rounded bg-amber-100 shadow-[0_0_6px_3px_rgba(239,68,68,.45)]" aria-hidden="true" />
          Corridor = est. affected stretch
        </div>
        {zoom < DETAIL_ZOOM && <div className="mt-2 border-t border-ss-border pt-1.5 text-[11px] text-ss-textmuted">Zoomed out: showing priority ≥35 and top {TOP_N_WHEN_ZOOMED_OUT}.</div>}
      </div>

      {children}
    </div>
  );
}
