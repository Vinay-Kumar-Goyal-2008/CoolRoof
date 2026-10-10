"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

interface Props {
  wards: GeoJSON.FeatureCollection;
  hotspots: GeoJSON.FeatureCollection | null;
  roofs: GeoJSON.FeatureCollection | null;
  wardCount: number;
  selected: string | null;
  onSelect: (wardId: string) => void;
}

// Colour-blind-safe sequential ramp (viridis): rank 1 (first to cool) = brightest.
const RAMP = ["#fde725", "#7ad151", "#22a884", "#2a788e", "#414487", "#440154"];

export function WardMap({ wards, hotspots, roofs, wardCount, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current) return;
    const bounds = new maplibregl.LngLatBounds();
    for (const f of wards.features) {
      const rings = (f.geometry as GeoJSON.Polygon).coordinates.flat();
      rings.forEach((c) => bounds.extend(c as [number, number]));
    }
    const m = new maplibregl.Map({
      container: container.current,
      // No external tiles: wards are drawn on a plain background (self-contained, offline-safe).
      style: { version: 8, sources: {}, layers: [
        { id: "bg", type: "background", paint: { "background-color": "#eef1f4" } }] },
      bounds, fitBoundsOptions: { padding: 24 }, attributionControl: false,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("wards", { type: "geojson", data: wards });
      const stops = RAMP.flatMap((color, i) => [1 + (i * (wardCount - 1)) / (RAMP.length - 1), color]);
      m.addLayer({ id: "wards-fill", type: "fill", source: "wards", paint: {
        "fill-color": ["case", ["==", ["typeof", ["get", "rank"]], "number"],
          ["interpolate", ["linear"], ["get", "rank"], ...stops], "#bdbdbd",
        ] as unknown as maplibregl.ExpressionSpecification,
        "fill-opacity": 0.85 } });
      m.addLayer({ id: "wards-line", type: "line", source: "wards", paint: {
        "line-color": "#ffffff", "line-width": 1.5 } });
      m.addLayer({ id: "wards-selected", type: "line", source: "wards",
        filter: ["==", ["get", "ward_id"], ""], paint: { "line-color": "#d7301f", "line-width": 3.5 } });
      // Labels are HTML markers: a symbol layer would need a glyph (font) server, and this
      // map is deliberately self-contained with no external requests.
      for (const f of wards.features) {
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
      if (hotspots) {
        m.addSource("hotspots", { type: "geojson", data: hotspots });
        m.addLayer({ id: "hotspots-line", type: "line", source: "hotspots", paint: {
          "line-color": "#d7301f", "line-width": 1.2, "line-dasharray": [2, 1] } });
      }
      m.addSource("roofs", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "roofs-fill", type: "fill", source: "roofs", paint: {
        "fill-color": "#0b3d91", "fill-opacity": 0.9 } });
      m.on("click", "wards-fill", (e) => {
        const id = e.features?.[0]?.properties?.ward_id;
        if (typeof id === "string") onSelectRef.current(id);
      });
      m.on("mouseenter", "wards-fill", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "wards-fill", () => { m.getCanvas().style.cursor = ""; });
    });
    return () => { m.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wards, hotspots, wardCount]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      if (m.getLayer("wards-selected")) {
        m.setFilter("wards-selected", ["==", ["get", "ward_id"], selected ?? ""]);
      }
      const src = m.getSource("roofs") as maplibregl.GeoJSONSource | undefined;
      src?.setData(roofs ?? { type: "FeatureCollection", features: [] });
    };
    if (m.isStyleLoaded()) apply(); else m.once("load", apply);
  }, [selected, roofs]);

  return <div ref={container} className="map" role="img" aria-label="Ward heat priority map" />;
}

export function Legend({ title, count }: { title: string; count: number }) {
  return (
    <div className="legend" aria-hidden="true">
      <span>{title}</span>
      <div className="legend-bar" style={{ background: `linear-gradient(90deg, ${RAMP.join(",")})` }} />
      <div className="legend-ends"><span>1</span><span>{count}</span></div>
    </div>
  );
}
