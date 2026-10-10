"use client";

import { useState } from "react";

import { fmt, useI18n } from "@/lib/i18n";

const SIZE_M = 30;
const GRID_M = 2;
const SNAP_M = 0.5;

export interface Outline {
  areaM2: number;
  /** GeoJSON Polygon (lon/lat) placed around the given centre, for the API's roof outline. */
  polygon: GeoJSON.Polygon;
}

function shoelace(pts: [number, number][]): number {
  let s = 0;
  pts.forEach(([x1, y1], i) => {
    const [x2, y2] = pts[(i + 1) % pts.length];
    s += x1 * y2 - x2 * y1;
  });
  return Math.abs(s) / 2;
}

/** Sketch a roof outline on a 2 m grid; the drawn shape sets the roof area and is drawn in the PDF. */
export function RoofSketch({
  centre,
  onUse,
}: {
  centre: { lat: number; lon: number };
  onUse: (o: Outline) => void;
}) {
  const { t } = useI18n();
  const [pts, setPts] = useState<[number, number][]>([]);
  const area = pts.length >= 3 ? shoelace(pts) : 0;

  function add(e: React.MouseEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const snap = (v: number) => Math.round(v / SNAP_M) * SNAP_M;
    const x = snap(((e.clientX - box.left) / box.width) * SIZE_M);
    const y = snap(((e.clientY - box.top) / box.height) * SIZE_M);
    setPts((p) => [...p, [Math.min(Math.max(x, 0), SIZE_M), Math.min(Math.max(y, 0), SIZE_M)]]);
  }

  function use() {
    const kx = 111_320 * Math.cos((centre.lat * Math.PI) / 180);
    const ring = pts.map(([x, y]) => [
      Number((centre.lon + (x - SIZE_M / 2) / kx).toFixed(7)),
      Number((centre.lat - (y - SIZE_M / 2) / 110_574).toFixed(7)),
    ]);
    onUse({ areaM2: Number(area.toFixed(1)), polygon: { type: "Polygon", coordinates: [[...ring, ring[0]]] } });
  }

  const lines = Array.from({ length: SIZE_M / GRID_M + 1 }, (_, i) => i * GRID_M);
  return (
    <div className="sketch">
      <h3>{t("sketchTitle")}</h3>
      <p className="muted small">{t("sketchHint")}</p>
      <svg
        viewBox={`0 0 ${SIZE_M} ${SIZE_M}`}
        className="sketch-grid"
        onClick={add}
        role="img"
        aria-label={t("sketchTitle")}
      >
        {lines.map((v) => (
          <g key={v}>
            <line x1={v} y1={0} x2={v} y2={SIZE_M} stroke="currentColor" strokeWidth="0.05" opacity="0.3" />
            <line x1={0} y1={v} x2={SIZE_M} y2={v} stroke="currentColor" strokeWidth="0.05" opacity="0.3" />
          </g>
        ))}
        {pts.length >= 2 && (
          <polygon
            points={pts.map((p) => p.join(",")).join(" ")}
            fill="#0b5cad"
            fillOpacity="0.25"
            stroke="#0b5cad"
            strokeWidth="0.25"
          />
        )}
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="0.4" fill="#0b5cad" />
        ))}
      </svg>
      <p className="small">{area > 0 ? `${fmt(area, 1)} m²` : "—"}</p>
      <div className="row">
        <button type="button" onClick={() => setPts((p) => p.slice(0, -1))} disabled={!pts.length}>
          {t("sketchUndo")}
        </button>
        <button type="button" onClick={() => setPts([])} disabled={!pts.length}>
          {t("sketchClear")}
        </button>
        <button type="button" onClick={use} disabled={pts.length < 3}>
          {t("sketchUse")}
        </button>
      </div>
    </div>
  );
}
