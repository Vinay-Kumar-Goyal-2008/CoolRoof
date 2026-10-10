"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState } from "react";

import type { ColorBy, LayerState } from "@/components/WardMap";
import { api, type RoofItem, type WardSummary, type WardsResponse } from "@/lib/api";

type Res<T> = UseQueryResult<T, Error>;
type Awaited2<F extends (...a: never[]) => unknown> = Awaited<ReturnType<F>>;

/** Shared city data for every /app screen: one set of queries, one selected ward. */
interface AppData {
  wards: Res<WardsResponse>;
  forecast: Res<Awaited2<typeof api.forecast>>;
  facilities: Res<GeoJSON.FeatureCollection>;
  fire: Res<Awaited2<typeof api.fire>>;
  pas: Res<Awaited2<typeof api.protectedAreas>>;
  alerts: Res<Awaited2<typeof api.alerts>>;
  ranked: WardSummary[];
  selected: string | null;
  selectedWard: WardSummary | null;
  pick: (id: string | null) => void;
  roofs: RoofItem[] | null;
  setRoofs: (r: RoofItem[] | null) => void;
  layers: LayerState;
  setLayers: React.Dispatch<React.SetStateAction<LayerState>>;
  colorBy: ColorBy;
  setColorBy: (c: ColorBy) => void;
  wardGeo: GeoJSON.FeatureCollection | null;
  roofGeo: GeoJSON.FeatureCollection | null;
  fireGeo: GeoJSON.FeatureCollection | null;
  paGeo: GeoJSON.FeatureCollection | null;
}

const Ctx = createContext<AppData | null>(null);

export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [roofs, setRoofs] = useState<RoofItem[] | null>(null);
  const [layers, setLayers] = useState<LayerState>({
    dlst: false, hotspots: true, facilities: false, fire: false, protectedAreas: false,
  });
  const [colorBy, setColorBy] = useState<ColorBy>("priority");

  const wards = useQuery({ queryKey: ["wards"], queryFn: api.wards });
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: api.forecast, retry: false });
  const facilities = useQuery({ queryKey: ["facilities"], queryFn: api.facilities, retry: false });
  const fire = useQuery({ queryKey: ["fire"], queryFn: api.fire, retry: false });
  const pas = useQuery({ queryKey: ["pas"], queryFn: api.protectedAreas, retry: false });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts(), refetchInterval: 60_000 });

  const selectedWard = wards.data?.wards.find((w) => w.ward_id === selected) ?? null;
  const ranked = useMemo(
    () => [...(wards.data?.wards ?? [])].sort((a, b) => (a.priority.rank ?? 99) - (b.priority.rank ?? 99)),
    [wards.data],
  );

  const roofGeo = useMemo<GeoJSON.FeatureCollection | null>(
    () =>
      roofs && {
        type: "FeatureCollection",
        features: roofs.map((r) => ({ type: "Feature", properties: { id: r.building_id }, geometry: r.geometry })),
      },
    [roofs],
  );

  // Ward polygons carry the summary fields the map colours by.
  const wardGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!wards.data) return null;
    const byId = new Map(wards.data.wards.map((w) => [w.ward_id, w]));
    return {
      ...wards.data.geojson,
      features: wards.data.geojson.features.map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          degradation_signal: byId.get(String(f.properties?.ward_id))?.degradation_signal ?? "insufficient_data",
        },
      })),
    };
  }, [wards.data]);

  const fireGeo = useMemo<GeoJSON.FeatureCollection | null>(
    () =>
      fire.data
        ? {
            type: "FeatureCollection",
            features: fire.data.events.map((e) => ({
              type: "Feature",
              properties: { fire_class: e.fire_class, confidence: e.confidence, date: e.acq_date },
              geometry: { type: "Point", coordinates: [e.lon, e.lat] },
            })),
          }
        : null,
    [fire.data],
  );

  const paGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!pas.data?.geojson) return null;
    const byId = new Map(pas.data.areas.map((a) => [a.pa_id, a]));
    return {
      ...pas.data.geojson,
      features: pas.data.geojson.features.map((f) => ({
        ...f,
        properties: { ...f.properties, pressure: byId.get(String(f.properties?.pa_id))?.pressure ?? "insufficient_data" },
      })),
    };
  }, [pas.data]);

  const value: AppData = {
    wards, forecast, facilities, fire, pas, alerts, ranked, selected, selectedWard,
    pick: (id) => { setSelected(id); setRoofs(null); },
    roofs, setRoofs, layers, setLayers, colorBy, setColorBy, wardGeo, roofGeo, fireGeo, paGeo,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppData(): AppData {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAppData outside AppDataProvider");
  return v;
}

/** Mean ΔLST across wards that have a numeric value. */
export function meanDlst(wards: WardSummary[]): number | null {
  const v = wards.map((w) => w.mean_dlst_c?.value).filter((x): x is number => typeof x === "number");
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

export function totalExposed(wards: WardSummary[]): number | null {
  const v = wards.map((w) => w.exposed_population?.value).filter((x): x is number => typeof x === "number");
  return v.length ? v.reduce((a, b) => a + b, 0) : null;
}
