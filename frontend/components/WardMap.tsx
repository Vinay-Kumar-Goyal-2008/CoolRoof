"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { useEffect, useRef } from "react";

export interface LayerState {
  dlst: boolean;
  hotspots: boolean;
  facilities: boolean;
  fire: boolean;
  protectedAreas: boolean;
}

export type ColorBy = "priority" | "degradation";

interface Props {
  wards: GeoJSON.FeatureCollection;
  hotspots: GeoJSON.FeatureCollection | null;
  roofs: GeoJSON.FeatureCollection | null;
  facilities: GeoJSON.FeatureCollection | null;
  fire: GeoJSON.FeatureCollection | null;
  protectedAreas: GeoJSON.FeatureCollection | null;
  tilesUrl: string | null;
  layers: LayerState;
  colorBy: ColorBy;
  wardCount: number;
  selected: string | null;
  onSelect: (wardId: string) => void;
}

// Colour-blind-safe sequential ramp (viridis): rank 1 (first to cool) = brightest.
export const RAMP = ["#fde725", "#7ad151", "#22a884", "#2a788e", "#414487", "#440154"];
export const DEGRADATION_COLORS: Record<string, string> = {
  none: "#d9f0d3",
  weak: "#fee08b",
  moderate: "#fdae61",
  strong: "#d73027",
  insufficient_data: "#cccccc",
  not_applicable: "#e5e7eb",
};

let protocolRegistered = false;
function ensurePmtiles(): void {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function fillColor(colorBy: ColorBy, wardCount: number): maplibregl.ExpressionSpecification {
  if (colorBy === "degradation") {
    return [
      "match",
      ["get", "degradation_signal"],
      ...Object.entries(DEGRADATION_COLORS).flat(),
      "#bdbdbd",
    ] as unknown as maplibregl.ExpressionSpecification;
  }
  const stops = RAMP.flatMap((color, i) => [1 + (i * (wardCount - 1)) / (RAMP.length - 1), color]);
  return [
    "case",
    ["==", ["typeof", ["get", "rank"]], "number"],
    ["interpolate", ["linear"], ["get", "rank"], ...stops],
    "#bdbdbd",
  ] as unknown as maplibregl.ExpressionSpecification;
}

export function WardMap(p: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const onSelectRef = useRef(p.onSelect);
  onSelectRef.current = p.onSelect;
  const live = useRef(p);
  live.current = p;

  useEffect(() => {
    if (!container.current) return;
    ensurePmtiles();
    const bounds = new maplibregl.LngLatBounds();
    for (const f of p.wards.features) {
      const rings = (f.geometry as GeoJSON.Polygon).coordinates.flat();
      rings.forEach((c) => bounds.extend(c as [number, number]));
    }
    const m = new maplibregl.Map({
      container: container.current,
      // No external basemap: wards are drawn on a plain background (self-contained, offline-safe).
      style: {
        version: 8,
        sources: {},
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#e9e2d6" } }],
      },
      bounds,
      fitBoundsOptions: { padding: 24 },
      attributionControl: false,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    m.on("load", () => {
      const cur = live.current;
      if (cur.tilesUrl) {
        m.addSource("dlst", { type: "raster", url: `pmtiles://${cur.tilesUrl}`, tileSize: 256 });
        m.addLayer({
          id: "dlst",
          type: "raster",
          source: "dlst",
          layout: { visibility: cur.layers.dlst ? "visible" : "none" },
        });
      }
      m.addSource("wards", { type: "geojson", data: cur.wards });
      m.addLayer({
        id: "wards-fill",
        type: "fill",
        source: "wards",
        paint: {
          "fill-color": fillColor(cur.colorBy, cur.wardCount),
          "fill-opacity": cur.layers.dlst ? 0.25 : 0.85,
        },
      });
      m.addLayer({
        id: "wards-line",
        type: "line",
        source: "wards",
        paint: { "line-color": "#ffffff", "line-width": 1.5 },
      });
      m.addLayer({
        id: "wards-selected",
        type: "line",
        source: "wards",
        filter: ["==", ["get", "ward_id"], ""],
        paint: { "line-color": "#d7301f", "line-width": 3.5 },
      });
      m.addSource("pa", { type: "geojson", data: cur.protectedAreas ?? EMPTY });
      m.addLayer({
        id: "pa-fill",
        type: "fill",
        source: "pa",
        layout: { visibility: cur.layers.protectedAreas ? "visible" : "none" },
        paint: {
          "fill-color": [
            "match",
            ["get", "pressure"],
            "low", "#86efac",
            "moderate", "#fde047",
            "high", "#f87171",
            "#d1d5db",
          ] as unknown as maplibregl.ExpressionSpecification,
          "fill-opacity": 0.55,
        },
      });
      m.addLayer({
        id: "pa-line",
        type: "line",
        source: "pa",
        layout: { visibility: cur.layers.protectedAreas ? "visible" : "none" },
        paint: { "line-color": "#166534", "line-width": 2, "line-dasharray": [3, 2] },
      });
      m.addSource("hotspots", { type: "geojson", data: cur.hotspots ?? EMPTY });
      m.addLayer({
        id: "hotspots-line",
        type: "line",
        source: "hotspots",
        layout: { visibility: cur.layers.hotspots ? "visible" : "none" },
        paint: { "line-color": "#d7301f", "line-width": 1.2, "line-dasharray": [2, 1] },
      });
      m.addSource("facilities", { type: "geojson", data: cur.facilities ?? EMPTY });
      m.addLayer({
        id: "facilities",
        type: "circle",
        source: "facilities",
        layout: { visibility: cur.layers.facilities ? "visible" : "none" },
        paint: {
          "circle-radius": ["match", ["get", "kind"], "hospital", 7, "cooling_point", 6, 4.5],
          "circle-color": [
            "match",
            ["get", "kind"],
            "hospital", "#0b5cad",
            "cooling_point", "#166534",
            "#6b21a8",
          ] as unknown as maplibregl.ExpressionSpecification,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      m.addSource("fire", { type: "geojson", data: cur.fire ?? EMPTY });
      m.addLayer({
        id: "fire",
        type: "circle",
        source: "fire",
        layout: { visibility: cur.layers.fire ? "visible" : "none" },
        paint: {
          "circle-radius": 7,
          "circle-color": [
            "match",
            ["get", "fire_class"],
            "forest_fire", "#b91c1c",
            "vegetation_fire", "#ea580c",
            "agricultural_burning_candidate", "#ca8a04",
            "urban_thermal_anomaly_candidate", "#7c3aed",
            "persistent_source", "#6b7280",
            "#92400e",
          ] as unknown as maplibregl.ExpressionSpecification,
          "circle-stroke-color": "#000000",
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });
      m.addSource("roofs", { type: "geojson", data: EMPTY });
      m.addLayer({
        id: "roofs-fill",
        type: "fill",
        source: "roofs",
        paint: { "fill-color": "#0b3d91", "fill-opacity": 0.9 },
      });

      // Labels are HTML markers: a symbol layer would need a glyph (font) server, and this
      // map is deliberately self-contained with no external requests.
      for (const f of cur.wards.features) {
        const coords = (f.geometry as GeoJSON.Polygon).coordinates[0] as [number, number][];
        const xs = coords.map((c) => c[0]);
        const ys = coords.map((c) => c[1]);
        const el = document.createElement("div");
        el.className = "ward-label";
        el.textContent = String(f.properties?.ward_id ?? "");
        new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2])
          .addTo(m);
      }

      m.on("click", "wards-fill", (e) => {
        const id = e.features?.[0]?.properties?.ward_id;
        if (typeof id === "string") onSelectRef.current(id);
      });
      m.on("mouseenter", "wards-fill", () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", "wards-fill", () => {
        m.getCanvas().style.cursor = "";
      });
      m.fire("coolroof-ready");
    });
    return () => {
      m.remove();
      map.current = null;
    };
    // The map is built once per ward set; the effects below keep it in sync with props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.wards]);

  // keep layers, data and styling in sync
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      const vis = (id: string, on: boolean) => {
        if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", on ? "visible" : "none");
      };
      vis("dlst", p.layers.dlst);
      vis("hotspots-line", p.layers.hotspots);
      vis("facilities", p.layers.facilities);
      vis("fire", p.layers.fire);
      vis("pa-fill", p.layers.protectedAreas);
      vis("pa-line", p.layers.protectedAreas);
      if (m.getLayer("wards-fill")) {
        m.setPaintProperty("wards-fill", "fill-color", fillColor(p.colorBy, p.wardCount));
        m.setPaintProperty("wards-fill", "fill-opacity", p.layers.dlst ? 0.25 : 0.85);
        m.setFilter("wards-selected", ["==", ["get", "ward_id"], p.selected ?? ""]);
      }
      const setData = (id: string, data: GeoJSON.FeatureCollection | null) =>
        (m.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data ?? EMPTY);
      setData("roofs", p.roofs);
      setData("facilities", p.facilities);
      setData("fire", p.fire);
      setData("pa", p.protectedAreas);
      setData("hotspots", p.hotspots);
    };
    if (m.getLayer("wards-fill")) apply();
    else (m as unknown as { once: (t: string, f: () => void) => void }).once("coolroof-ready", apply);
  }, [p.layers, p.colorBy, p.selected, p.roofs, p.facilities, p.fire, p.protectedAreas, p.hotspots, p.wardCount]);

  return <div ref={container} className="map" role="img" aria-label="Ward heat priority map" />;
}

export function Legend({
  title,
  count,
  colorBy,
}: {
  title: string;
  count: number;
  colorBy: ColorBy;
}) {
  if (colorBy === "degradation") {
    return (
      <div className="legend" aria-hidden="true">
        <span>{title}</span>
        <div className="legend-chips">
          {Object.entries(DEGRADATION_COLORS).map(([k, c]) => (
            <span key={k} className="chip">
              <i style={{ background: c }} />
              {k.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="legend" aria-hidden="true">
      <span>{title}</span>
      <div className="legend-bar" style={{ background: `linear-gradient(90deg, ${RAMP.join(",")})` }} />
      <div className="legend-ends">
        <span>1</span>
        <span>{count}</span>
      </div>
    </div>
  );
}
