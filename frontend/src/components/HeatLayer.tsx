import L from 'leaflet';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import type { HeatmapPoint } from '../types';

// Colour ramp for report density: transparent teal -> amber -> red.
const STOPS: [number, [number, number, number]][] = [
  [0.0, [34, 211, 238]],
  [0.45, [45, 212, 191]],
  [0.7, [250, 204, 21]],
  [1.0, [239, 68, 68]],
];

function buildPalette(): Uint8ClampedArray {
  const palette = new Uint8ClampedArray(256 * 3);
  for (let index = 0; index < 256; index += 1) {
    const t = index / 255;
    const upper = STOPS.findIndex(([stop]) => stop >= t);
    const [t1, c1] = STOPS[Math.max(0, upper - 1)];
    const [t2, c2] = STOPS[Math.max(0, upper)];
    const mix = t2 === t1 ? 0 : (t - t1) / (t2 - t1);
    for (let channel = 0; channel < 3; channel += 1) palette[index * 3 + channel] = c1[channel] + (c2[channel] - c1[channel]) * mix;
  }
  return palette;
}

/** Minimal canvas heat layer (same approach as simpleheat) so no extra dependency is needed. */
class HeatCanvasLayer extends L.Layer {
  private canvas: HTMLCanvasElement | null = null;
  private points: HeatmapPoint[] = [];
  private readonly palette = buildPalette();
  private stamps = new Map<number, HTMLCanvasElement>();

  constructor(private readonly maxOpacity = 0.42) {
    super();
  }

  setPoints(points: HeatmapPoint[]) {
    this.points = points;
    this.redraw();
  }

  onAdd(map: L.Map) {
    this.canvas = L.DomUtil.create('canvas', 'leaflet-zoom-hide ss-heat-layer') as HTMLCanvasElement;
    this.canvas.style.pointerEvents = 'none';
    // Own pane below the vector overlay pane (z 400) so markers and corridors always draw on top.
    const pane = map.getPane('ss-heat') ?? map.createPane('ss-heat');
    pane.style.zIndex = '350';
    pane.style.pointerEvents = 'none';
    pane.appendChild(this.canvas);
    map.on('moveend zoomend resize viewreset', this.redraw, this);
    this.redraw();
    return this;
  }

  onRemove(map: L.Map) {
    map.off('moveend zoomend resize viewreset', this.redraw, this);
    this.canvas?.remove();
    this.canvas = null;
    return this;
  }

  private stamp(radius: number) {
    let stamp = this.stamps.get(radius);
    if (!stamp) {
      stamp = document.createElement('canvas');
      stamp.width = stamp.height = radius * 2;
      const context = stamp.getContext('2d')!;
      const gradient = context.createRadialGradient(radius, radius, 0, radius, radius, radius);
      gradient.addColorStop(0, 'rgba(0,0,0,1)');
      gradient.addColorStop(1, 'rgba(0,0,0,0)');
      context.fillStyle = gradient;
      context.fillRect(0, 0, radius * 2, radius * 2);
      this.stamps.set(radius, stamp);
    }
    return stamp;
  }

  redraw() {
    const map = this._map as L.Map | undefined;
    if (!map || !this.canvas) return;
    const size = map.getSize();
    if (size.x === 0 || size.y === 0) return;
    this.canvas.width = size.x;
    this.canvas.height = size.y;
    L.DomUtil.setPosition(this.canvas, map.containerPointToLayerPoint([0, 0]));
    const context = this.canvas.getContext('2d', { willReadFrequently: true });
    if (!context) return;
    context.clearRect(0, 0, size.x, size.y);
    const zoom = map.getZoom();
    const radius = Math.round(Math.max(10, Math.min(30, 10 + (zoom - 11) * 5)));
    // Street level: heat recedes so corridors and markers stay the primary symbols.
    const fade = zoom >= 15 ? 0.45 : zoom >= 14 ? 0.7 : 1;
    const stamp = this.stamp(radius);
    for (const [lat, lon, weight] of this.points) {
      const point = map.latLngToContainerPoint([lat, lon]);
      if (point.x < -radius || point.y < -radius || point.x > size.x + radius || point.y > size.y + radius) continue;
      context.globalAlpha = Math.min(1, (0.1 + weight * 0.3) * fade);
      context.drawImage(stamp, point.x - radius, point.y - radius);
    }
    const image = context.getImageData(0, 0, size.x, size.y);
    const pixels = image.data;
    for (let index = 3; index < pixels.length; index += 4) {
      const alpha = pixels[index];
      if (!alpha) continue;
      const offset = alpha * 3;
      pixels[index - 3] = this.palette[offset];
      pixels[index - 2] = this.palette[offset + 1];
      pixels[index - 1] = this.palette[offset + 2];
      pixels[index] = Math.min(255, alpha * this.maxOpacity * 1.6);
    }
    context.putImageData(image, 0, 0);
  }
}

export function HeatLayer({ points, visible }: { points: HeatmapPoint[]; visible: boolean }) {
  const map = useMap();
  const layer = useRef<HeatCanvasLayer | null>(null);
  useEffect(() => {
    layer.current = new HeatCanvasLayer();
    return () => {
      layer.current?.remove();
      layer.current = null;
    };
  }, []);
  useEffect(() => {
    const current = layer.current;
    if (!current) return;
    if (visible && !map.hasLayer(current)) current.addTo(map);
    if (!visible && map.hasLayer(current)) current.remove();
  }, [map, visible]);
  useEffect(() => {
    layer.current?.setPoints(points);
  }, [points]);
  return null;
}
