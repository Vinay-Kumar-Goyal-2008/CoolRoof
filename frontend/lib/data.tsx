"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState } from "react";

import type { ColorBy, LayerState } from "@/components/WardMap";
import { api, type RoofItem, type WardSummary, type WardsResponse } from "@/lib/api";
import {
  DELHI_FACILITIES_GEOJSON,
  DELHI_HOTSPOTS_GEOJSON,
  DELHI_ROOFS_GEOJSON,
  DELHI_WARDS_GEOJSON,
  DELHI_WARDS_RESPONSE,
  DELHI_WARDS_SUMMARY,
} from "@/lib/delhi_data";

type Res<T> = UseQueryResult<T, Error>;
type Awaited2<F extends (...a: never[]) => unknown> = Awaited<ReturnType<F>>;

export type CitySlug = "mini_city" | "delhi";

/** Shared city data for every /app screen: one set of queries, one selected ward. */
interface AppData {
  city: CitySlug;
  setCity: (c: CitySlug) => void;
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
  hotspotsGeo: GeoJSON.FeatureCollection | null;
}

const Ctx = createContext<AppData | null>(null);

export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const [city, setCityState] = useState<CitySlug>("delhi"); // Default to real Delhi MCD administrative zones!
  const [selected, setSelected] = useState<string | null>(null);
  const [roofs, setRoofs] = useState<RoofItem[] | null>(null);
  const [layers, setLayers] = useState<LayerState>({
    dlst: false,
    hotspots: true,
    facilities: true,
    fire: false,
    protectedAreas: false,
  });
  const [colorBy, setColorBy] = useState<ColorBy>("priority");

  const setCity = (c: CitySlug) => {
    setCityState(c);
    setSelected(null);
    setRoofs(null);
  };

  const wardsQuery = useQuery({ queryKey: ["wards"], queryFn: api.wards, enabled: city === "mini_city" });
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: api.forecast, retry: false });
  const facilitiesQuery = useQuery({ queryKey: ["facilities"], queryFn: api.facilities, retry: false, enabled: city === "mini_city" });
  const fire = useQuery({ queryKey: ["fire"], queryFn: api.fire, retry: false });
  const pas = useQuery({ queryKey: ["pas"], queryFn: api.protectedAreas, retry: false });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts(), refetchInterval: 60_000 });

  // Effective wards response (Delhi mock/curated vs backend mini_city)
  const wards = useMemo<Res<WardsResponse>>(() => {
    if (city === "delhi") {
      return {
        data: DELHI_WARDS_RESPONSE,
        isLoading: false,
        isSuccess: true,
        isError: false,
        error: null,
        status: "success",
      } as unknown as Res<WardsResponse>;
    }
    return wardsQuery;
  }, [city, wardsQuery]);

  const facilities = useMemo<Res<GeoJSON.FeatureCollection>>(() => {
    if (city === "delhi") {
      return {
        data: DELHI_FACILITIES_GEOJSON,
        isLoading: false,
        isSuccess: true,
        isError: false,
        error: null,
        status: "success",
      } as unknown as Res<GeoJSON.FeatureCollection>;
    }
    return facilitiesQuery;
  }, [city, facilitiesQuery]);

  const selectedWard = useMemo(() => {
    if (!selected) return null;
    const list = city === "delhi" ? DELHI_WARDS_SUMMARY : (wards.data?.wards ?? []);
    return list.find((w) => w.ward_id === selected) ?? null;
  }, [city, selected, wards.data]);

  const ranked = useMemo(() => {
    const list = city === "delhi" ? DELHI_WARDS_SUMMARY : (wards.data?.wards ?? []);
    return [...list].sort((a, b) => (a.priority.rank ?? 99) - (b.priority.rank ?? 99));
  }, [city, wards.data]);

  const roofGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (city === "delhi") {
      return DELHI_ROOFS_GEOJSON;
    }
    return (
      roofs && {
        type: "FeatureCollection",
        features: roofs.map((r) => ({ type: "Feature", properties: { id: r.building_id, rank: r.rank }, geometry: r.geometry })),
      }
    );
  }, [city, roofs]);

  const wardGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (city === "delhi") {
      return DELHI_WARDS_GEOJSON;
    }
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
  }, [city, wards.data]);

  const hotspotsGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (city === "delhi") {
      return DELHI_HOTSPOTS_GEOJSON;
    }
    return wards.data?.hotspots ?? null;
  }, [city, wards.data]);

  const fireGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (city === "delhi") {
      return {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { fire_class: "urban_thermal_anomaly_candidate", confidence: "high", date: "2026-05-18" },
            geometry: { type: "Point", coordinates: [77.228, 28.654] },
          },
        ],
      };
    }
    return fire.data
      ? {
          type: "FeatureCollection",
          features: fire.data.events.map((e) => ({
            type: "Feature",
            properties: { fire_class: e.fire_class, confidence: e.confidence, date: e.acq_date },
            geometry: { type: "Point", coordinates: [e.lon, e.lat] },
          })),
        }
      : null;
  }, [city, fire.data]);

  const paGeo = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (city === "delhi") {
      return {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { name: "Central Ridge Reserve Forest", pressure: "moderate" },
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [77.172, 28.608],
                  [77.185, 28.625],
                  [77.198, 28.618],
                  [77.188, 28.598],
                  [77.172, 28.608],
                ],
              ],
            },
          },
          {
            type: "Feature",
            properties: { name: "Asola Bhatti Wildlife Sanctuary", pressure: "low" },
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [77.215, 28.455],
                  [77.245, 28.475],
                  [77.265, 28.448],
                  [77.235, 28.435],
                  [77.215, 28.455],
                ],
              ],
            },
          },
        ],
      };
    }
    if (!pas.data?.geojson) return null;
    const byId = new Map(pas.data.areas.map((a) => [a.pa_id, a]));
    return {
      ...pas.data.geojson,
      features: pas.data.geojson.features.map((f) => ({
        ...f,
        properties: { ...f.properties, pressure: byId.get(String(f.properties?.pa_id))?.pressure ?? "insufficient_data" },
      })),
    };
  }, [city, pas.data]);

  const value: AppData = {
    city,
    setCity,
    wards,
    forecast,
    facilities,
    fire,
    pas,
    alerts,
    ranked,
    selected,
    selectedWard,
    pick: (id) => {
      setSelected(id);
      setRoofs(null);
    },
    roofs,
    setRoofs,
    layers,
    setLayers,
    colorBy,
    setColorBy,
    wardGeo,
    roofGeo,
    fireGeo,
    paGeo,
    hotspotsGeo,
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
