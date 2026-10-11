"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";

export interface LayerState {
  dlst: boolean;
  hotspots: boolean;
  facilities: boolean;
  fire: boolean;
  protectedAreas: boolean;
}

export type ColorBy = "priority" | "degradation";
export type BasemapMode = "streets" | "satellite" | "dark" | "clean";

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
  opacity?: number;
  onOpacityChange?: (o: number) => void;
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

// 1. OpenFreeMap Liberty (Streets)
const OSM_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

// 2. High-Resolution ESRI World Imagery (Satellite)
const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "esri-satellite": {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      attribution: "&copy; Esri World Imagery",
    },
  },
  layers: [
    {
      id: "esri-sat",
      type: "raster",
      source: "esri-satellite",
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

// 3. Sleek CARTO Dark Matter (Dark Mode)
const DARK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "carto-dark": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    },
  },
  layers: [
    {
      id: "carto-dark-layer",
      type: "raster",
      source: "carto-dark",
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

// 4. Minimalist CARTO Positron (Clean Light)
const CLEAN_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "carto-clean": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    },
  },
  layers: [
    {
      id: "carto-clean-layer",
      type: "raster",
      source: "carto-clean",
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

// Fallback style for offline resilience
const FALLBACK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#17100c" } }],
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

function haversineDistance(c1: [number, number], c2: [number, number]): number {
  const R = 6371000; // meters
  const dLat = ((c2[1] - c1[1]) * Math.PI) / 180;
  const dLon = ((c2[0] - c1[0]) * Math.PI) / 180;
  const lat1 = (c1[1] * Math.PI) / 180;
  const lat2 = (c2[1] * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.sin(dLon / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(a));
}

export function WardMap(p: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const popup = useRef<maplibregl.Popup | null>(null);
  const onSelectRef = useRef(p.onSelect);
  onSelectRef.current = p.onSelect;
  const live = useRef(p);
  live.current = p;

  const [basemap, setBasemap] = useState<BasemapMode>("streets");
  const [opacity, setOpacity] = useState<number>(p.opacity ?? 0.72);
  const [is3D, setIs3D] = useState<boolean>(false);
  const [measuring, setMeasuring] = useState<boolean>(false);
  const [measurePts, setMeasurePts] = useState<[number, number][]>([]);
  const [measureDist, setMeasureDist] = useState<number | null>(null);

  // Keep internal opacity in sync if prop changes
  useEffect(() => {
    if (typeof p.opacity === "number") setOpacity(p.opacity);
  }, [p.opacity]);

  // Construct map instance
  useEffect(() => {
    if (!container.current) return;
    ensurePmtiles();

    const bounds = new maplibregl.LngLatBounds();
    for (const f of p.wards.features) {
      if (f.geometry.type === "Polygon") {
        const rings = (f.geometry as GeoJSON.Polygon).coordinates.flat();
        rings.forEach((c) => bounds.extend(c as [number, number]));
      } else if (f.geometry.type === "MultiPolygon") {
        const rings = (f.geometry as GeoJSON.MultiPolygon).coordinates.flat(2);
        rings.forEach((c) => bounds.extend(c as [number, number]));
      }
    }

    const m = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE_URL,
      bounds,
      fitBoundsOptions: { padding: 28 },
      attributionControl: { compact: true },
    });
    map.current = m;

    m.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    m.addControl(new maplibregl.FullscreenControl(), "top-right");

    popup.current = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 14,
      className: "coolroof-map-popup",
    });

    const initLayers = () => {
      const cur = live.current;
      if (m.getSource("wards")) return; // already loaded

      if (cur.tilesUrl) {
        m.addSource("dlst", { type: "raster", url: `pmtiles://${cur.tilesUrl}`, tileSize: 256 });
        m.addLayer({
          id: "dlst",
          type: "raster",
          source: "dlst",
          layout: { visibility: cur.layers.dlst ? "visible" : "none" },
          paint: { "raster-opacity": opacity },
        });
      }

      m.addSource("wards", { type: "geojson", data: cur.wards });
      m.addLayer({
        id: "wards-fill",
        type: "fill",
        source: "wards",
        paint: {
          "fill-color": fillColor(cur.colorBy, cur.wardCount),
          "fill-opacity": cur.layers.dlst ? Math.max(0.15, opacity * 0.3) : opacity,
        },
      });
      m.addLayer({
        id: "wards-line",
        type: "line",
        source: "wards",
        paint: { "line-color": "#ffffff", "line-width": 1.6, "line-opacity": 0.8 },
      });
      m.addLayer({
        id: "wards-selected",
        type: "line",
        source: "wards",
        filter: ["==", ["get", "ward_id"], ""],
        paint: { "line-color": "#f0a040", "line-width": 3.8 },
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
          "fill-opacity": 0.5,
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
        paint: { "line-color": "#f2736b", "line-width": 2, "line-dasharray": [2, 1] },
      });

      m.addSource("facilities", { type: "geojson", data: cur.facilities ?? EMPTY });
      m.addLayer({
        id: "facilities",
        type: "circle",
        source: "facilities",
        layout: { visibility: cur.layers.facilities ? "visible" : "none" },
        paint: {
          "circle-radius": ["match", ["get", "kind"], "hospital", 7.5, "cooling_point", 6.5, 5],
          "circle-color": [
            "match",
            ["get", "kind"],
            "hospital", "#38bdf8",
            "cooling_point", "#34d399",
            "#a855f7",
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
          "circle-color": "#ea580c",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.2,
          "circle-opacity": 0.9,
        },
      });

      m.addSource("roofs", { type: "geojson", data: cur.roofs ?? EMPTY });
      m.addLayer({
        id: "roofs-fill",
        type: "fill",
        source: "roofs",
        layout: { visibility: is3D ? "none" : "visible" },
        paint: { "fill-color": "#f0a040", "fill-opacity": 0.85 },
      });
      m.addLayer({
        id: "roofs-3d",
        type: "fill-extrusion",
        source: "roofs",
        layout: { visibility: is3D ? "visible" : "none" },
        paint: {
          "fill-extrusion-color": [
            "match",
            ["get", "rank"],
            1, "#f59e0b",
            2, "#ef4444",
            3, "#3b82f6",
            "#10b981",
          ] as unknown as maplibregl.ExpressionSpecification,
          "fill-extrusion-height": 35,
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.92,
        },
      });

      // Measurement line source
      m.addSource("measure-line", { type: "geojson", data: EMPTY });
      m.addLayer({
        id: "measure-line-layer",
        type: "line",
        source: "measure-line",
        paint: { "line-color": "#f0a040", "line-width": 3, "line-dasharray": [2, 2] },
      });

      // Hover Tooltip
      m.on("mousemove", "wards-fill", (e) => {
        if (!e.features?.length) return;
        const feat = e.features[0];
        const wardId = feat.properties?.ward_id;
        const wardName = feat.properties?.name ?? wardId;
        const rank = feat.properties?.rank ?? "—";
        const dlst = feat.properties?.mean_dlst_c ?? "—";
        const pop = feat.properties?.population ?? "—";
        const deg = feat.properties?.degradation_signal ?? "—";

        m.getCanvas().style.cursor = "pointer";
        popup.current
          ?.setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-family: inherit; font-size: 13px; line-height: 1.4; color: #f6ead9; background: #1a120d; padding: 10px 14px; border: 1px solid #4a3322; border-radius: 10px; box-shadow: 0 10px 24px rgba(0,0,0,0.6);">
              <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px; display: flex; justify-content: space-between; gap: 8px;">
                <span>${wardName}</span>
                <span style="background: rgba(240,160,64,0.2); color: #f0a040; padding: 1px 6px; border-radius: 4px; font-size: 11px;">Rank #${rank}</span>
              </div>
              <div style="color: #a09080; font-size: 12px; margin-bottom: 2px;">ID: <b style="color: #d2c4b2;">${wardId}</b></div>
              <div style="color: #a09080; font-size: 12px; margin-bottom: 2px;">ΔLST Anomaly: <b style="color: #f2736b;">${typeof dlst === "number" ? dlst.toFixed(1) + " °C" : dlst}</b></div>
              <div style="color: #a09080; font-size: 12px;">Population: <b style="color: #d2c4b2;">${typeof pop === "number" ? pop.toLocaleString() : pop}</b></div>
            </div>`
          )
          .addTo(m);
      });

      m.on("mouseleave", "wards-fill", () => {
        m.getCanvas().style.cursor = "";
        popup.current?.remove();
      });

      m.on("click", "wards-fill", (e) => {
        const id = e.features?.[0]?.properties?.ward_id;
        if (typeof id === "string") onSelectRef.current(id);
      });

      m.fire("coolroof-ready");
    };

    // Style error fallback
    m.on("error", () => {
      if (!m.getSource("wards")) {
        m.setStyle(FALLBACK_STYLE);
        m.once("styledata", initLayers);
      }
    });

    const timer = window.setTimeout(() => {
      if (!m.getSource("wards")) {
        m.setStyle(FALLBACK_STYLE);
        m.once("styledata", initLayers);
      }
    }, 7000);

    m.on("load", () => {
      clearTimeout(timer);
      initLayers();
    });

    return () => {
      clearTimeout(timer);
      popup.current?.remove();
      m.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.wards]);

  // Sync layers & props
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
        m.setPaintProperty("wards-fill", "fill-opacity", p.layers.dlst ? Math.max(0.15, opacity * 0.3) : opacity);
        m.setFilter("wards-selected", ["==", ["get", "ward_id"], p.selected ?? ""]);
      }
      if (m.getLayer("dlst")) {
        m.setPaintProperty("dlst", "raster-opacity", opacity);
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
  }, [p.layers, p.colorBy, p.selected, p.roofs, p.facilities, p.fire, p.protectedAreas, p.hotspots, p.wardCount, opacity]);

  // Handle Basemap Switcher
  const handleBasemapChange = (mode: BasemapMode) => {
    setBasemap(mode);
    const m = map.current;
    if (!m) return;

    let targetStyle: string | maplibregl.StyleSpecification = OSM_STYLE_URL;
    if (mode === "satellite") targetStyle = SATELLITE_STYLE;
    else if (mode === "dark") targetStyle = DARK_STYLE;
    else if (mode === "clean") targetStyle = CLEAN_STYLE;

    m.setStyle(targetStyle);
    m.once("styledata", () => {
      // Re-trigger load event to re-add all analytical layers
      m.fire("load");
    });
  };

  // Toggle 3D Extrusion
  const toggle3D = () => {
    const next = !is3D;
    setIs3D(next);
    const m = map.current;
    if (!m) return;
    if (m.getLayer("roofs-3d")) {
      m.setLayoutProperty("roofs-3d", "visibility", next ? "visible" : "none");
    }
    if (m.getLayer("roofs-fill")) {
      m.setLayoutProperty("roofs-fill", "visibility", next ? "none" : "visible");
    }
    m.easeTo({
      pitch: next ? 55 : 0,
      bearing: next ? -20 : 0,
      duration: 800,
    });
  };

  // Measurement Tool Click Handler
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    const onMapClick = (e: maplibregl.MapMouseEvent) => {
      if (!measuring) return;
      const pt: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (measurePts.length === 0 || measurePts.length === 2) {
        setMeasurePts([pt]);
        setMeasureDist(null);
        (m.getSource("measure-line") as maplibregl.GeoJSONSource | undefined)?.setData(EMPTY);
      } else if (measurePts.length === 1) {
        const p1 = measurePts[0];
        const p2 = pt;
        setMeasurePts([p1, p2]);
        const d = haversineDistance(p1, p2);
        setMeasureDist(d);
        (m.getSource("measure-line") as maplibregl.GeoJSONSource | undefined)?.setData({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              properties: {},
              geometry: { type: "LineString", coordinates: [p1, p2] },
            },
          ],
        });
      }
    };

    m.on("click", onMapClick);
    return () => {
      m.off("click", onMapClick);
    };
  }, [measuring, measurePts]);

  return (
    <div style={{ position: "relative", width: "100%" }}>
      {/* Floating Map Controls Toolbar */}
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          zIndex: 10,
          display: "flex",
          gap: 6,
          flexWrap: "wrap",
          background: "rgba(23, 16, 12, 0.88)",
          backdropFilter: "blur(8px)",
          border: "1px solid #34251a",
          borderRadius: "12px",
          padding: "4px 8px",
          alignItems: "center",
          maxWidth: "calc(100% - 20px)",
        }}
      >
        {/* Basemap Switcher */}
        <div style={{ display: "inline-flex", gap: 3, alignItems: "center" }}>
          {(
            [
              ["streets", "🗺️ Streets"],
              ["satellite", "🛰️ Satellite"],
              ["dark", "🌙 Dark"],
              ["clean", "☀️ Clean"],
            ] as [BasemapMode, string][]
          ).map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              style={{
                minHeight: 28,
                padding: "3px 9px",
                fontSize: "11px",
                borderRadius: "8px",
                background: basemap === mode ? "var(--accent)" : "transparent",
                color: basemap === mode ? "var(--accent-ink)" : "var(--ink)",
                border: "none",
                fontWeight: basemap === mode ? 600 : 400,
              }}
              onClick={() => handleBasemapChange(mode)}
            >
              {label}
            </button>
          ))}
        </div>

        <span style={{ width: 1, height: 16, background: "var(--line-2)" }} />

        {/* 3D Extrusion Toggle */}
        <button
          type="button"
          style={{
            minHeight: 28,
            padding: "3px 9px",
            fontSize: "11px",
            borderRadius: "8px",
            background: is3D ? "var(--accent)" : "transparent",
            color: is3D ? "var(--accent-ink)" : "var(--ink)",
            border: "none",
            fontWeight: is3D ? 600 : 400,
          }}
          onClick={toggle3D}
          title="Toggle 3D perspective and extruded cool-roof buildings"
        >
          {is3D ? "🧊 3D On" : "🏢 3D Off"}
        </button>

        <span style={{ width: 1, height: 16, background: "var(--line-2)" }} />

        {/* Measure Distance Tool */}
        <button
          type="button"
          style={{
            minHeight: 28,
            padding: "3px 9px",
            fontSize: "11px",
            borderRadius: "8px",
            background: measuring ? "var(--accent)" : "transparent",
            color: measuring ? "var(--accent-ink)" : "var(--ink)",
            border: "none",
            fontWeight: measuring ? 600 : 400,
          }}
          onClick={() => {
            const next = !measuring;
            setMeasuring(next);
            if (!next) {
              setMeasurePts([]);
              setMeasureDist(null);
              const m = map.current;
              (m?.getSource("measure-line") as maplibregl.GeoJSONSource | undefined)?.setData(EMPTY);
            }
          }}
          title="Click two points on the map to measure linear distance"
        >
          📏 {measuring ? "Measuring..." : "Measure"}
        </button>

        {measureDist !== null && (
          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--accent)" }}>
            {measureDist > 1000 ? `${(measureDist / 1000).toFixed(2)} km` : `${Math.round(measureDist)} m`}
          </span>
        )}

        <span style={{ width: 1, height: 16, background: "var(--line-2)" }} />

        {/* Interactive Heat Opacity Slider */}
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "11px", color: "var(--muted)" }}>
          <span>Opacity:</span>
          <input
            type="range"
            min="0.1"
            max="1.0"
            step="0.05"
            value={opacity}
            style={{ width: 70, height: 4, cursor: "pointer", accentColor: "var(--accent)", minHeight: 0 }}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              setOpacity(val);
              p.onOpacityChange?.(val);
            }}
          />
          <span style={{ width: 26, color: "var(--ink)", fontWeight: 500 }}>{Math.round(opacity * 100)}%</span>
        </div>
      </div>

      <div ref={container} className="map" role="img" aria-label="Ward heat priority map" />
    </div>
  );
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
