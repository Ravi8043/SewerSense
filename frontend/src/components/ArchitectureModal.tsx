import { CloseButton, useDialog } from './shared';

interface Props {
  open: boolean;
  onClose: () => void;
}

type Box = { x: number; y: number; w: number; h: number; title: string; sub: string; future?: boolean; accent?: boolean };

const BOXES: Box[] = [
  { x: 20, y: 40, w: 150, h: 46, title: 'Synthetic generator', sub: 'demo complaints (today)', accent: true },
  { x: 20, y: 100, w: 150, h: 46, title: 'Complaint systems', sub: 'HMWSSB call centre, portal', future: true },
  { x: 20, y: 160, w: 150, h: 46, title: 'Social / WhatsApp', sub: 'live adapters', future: true },
  { x: 20, y: 220, w: 150, h: 46, title: 'IoT level sensors', sub: 'manhole telemetry', future: true },
  { x: 225, y: 70, w: 170, h: 66, title: 'Hybrid extraction', sub: 'rules + LLM → validate → reconcile' },
  { x: 225, y: 160, w: 170, h: 46, title: 'Gazetteer', sub: 'localities, roads, landmarks' },
  { x: 450, y: 40, w: 160, h: 46, title: 'De-duplication', sub: 'same handle, TF-IDF > 0.8' },
  { x: 450, y: 100, w: 160, h: 46, title: 'Online clustering', sub: 'content · proximity · time · type' },
  { x: 450, y: 160, w: 160, h: 46, title: 'Scoring', sub: 'corridor, velocity, priority' },
  { x: 450, y: 220, w: 160, h: 46, title: 'GIS / network data', sub: 'road snapping, assets', future: true },
  { x: 665, y: 70, w: 140, h: 46, title: 'SQLite', sub: 'PostGIS later', accent: true },
  { x: 665, y: 140, w: 140, h: 46, title: 'FastAPI', sub: '/api/* JSON' },
  { x: 665, y: 210, w: 140, h: 56, title: 'Command center', sub: 'React · Leaflet', accent: true },
];

const ARROWS: [number, number, number, number, boolean?][] = [
  [170, 63, 225, 95],
  [170, 123, 225, 110, true],
  [170, 183, 225, 120, true],
  [310, 160, 310, 136],
  [395, 95, 450, 63],
  [530, 86, 530, 100],
  [530, 146, 530, 160],
  [530, 220, 530, 206, true],
  [610, 183, 665, 100],
  [735, 116, 735, 140],
  [735, 186, 735, 210],
];

export function ArchitectureModal({ open, onClose }: Props) {
  const ref = useDialog<HTMLDivElement>(open, onClose);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/60 p-4" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="arch-title" className="w-full max-w-[900px] rounded-lg border border-ss-border bg-ss-bg shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-ss-border bg-ss-panel p-4">
          <div>
            <h2 id="arch-title" className="text-[16px] font-semibold text-ss-text">How SewerSense works</h2>
            <p className="text-[12px] text-ss-textmuted">An intelligence layer above existing complaint and GIS systems — it does not replace them.</p>
          </div>
          <CloseButton onClick={onClose} label="Close architecture" />
        </div>
        <div className="p-4">
          <svg viewBox="0 0 825 290" className="w-full" role="img" aria-label="Pipeline from complaint sources through extraction, deduplication, clustering and scoring to the command center">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0 0 10 5 0 10z" fill="#475569" />
              </marker>
            </defs>
            {ARROWS.map(([x1, y1, x2, y2, future], index) => (
              <line key={index} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#475569" strokeWidth="1.5" strokeDasharray={future ? '4 4' : undefined} markerEnd="url(#arrow)" />
            ))}
            {BOXES.map((box) => (
              <g key={box.title} opacity={box.future ? 0.75 : 1}>
                <rect x={box.x} y={box.y} width={box.w} height={box.h} rx="6" fill={box.future ? 'transparent' : '#111821'} stroke={box.accent ? '#22d3ee' : box.future ? '#64748b' : '#334155'} strokeDasharray={box.future ? '5 4' : undefined} />
                <text x={box.x + box.w / 2} y={box.y + (box.h > 50 ? 26 : 20)} textAnchor="middle" fontSize="13" fontWeight="600" fill={box.future ? '#94a3b8' : '#e2e8f0'}>{box.title}</text>
                <text x={box.x + box.w / 2} y={box.y + (box.h > 50 ? 44 : 36)} textAnchor="middle" fontSize="11" fill="#94a3b8">{box.sub}</text>
                {box.future && <text x={box.x + box.w - 6} y={box.y + 12} textAnchor="end" fontSize="9" fontWeight="700" fill="#f59e0b">FUTURE</text>}
              </g>
            ))}
          </svg>
          <div className="mt-3 grid grid-cols-3 gap-3 text-[12px] text-ss-textmuted">
            <div className="rounded border border-ss-border p-3">
              <div className="mb-1 font-semibold text-ss-text">Built today</div>
              Synthetic reports flow through hybrid extraction, de-duplication, online clustering and explainable scoring into SQLite, served by FastAPI.
            </div>
            <div className="rounded border border-ss-border p-3">
              <div className="mb-1 font-semibold text-ss-text">Safety rails</div>
              LLM output is schema-validated and reconciled against the gazetteer; coordinates never come from the model. No key → deterministic rules mode.
            </div>
            <div className="rounded border border-dashed border-ss-border p-3">
              <div className="mb-1 font-semibold text-amber-300">Future (not implemented)</div>
              Live complaint and social adapters, IoT sensors, GIS road snapping, PostGIS and embeddings can feed the same extraction contract.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
