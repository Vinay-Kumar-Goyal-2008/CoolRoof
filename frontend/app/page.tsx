"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { PlannerConsole } from "@/components/PlannerConsole";
import { SignalsPanel } from "@/components/SignalsPanel";
import { SolarCard } from "@/components/SolarCard";
import type { ColorBy, LayerState } from "@/components/WardMap";
import { WardPanel } from "@/components/WardPanel";
import { api, type RoofItem } from "@/lib/api";
import { fmt, useI18n, type Key } from "@/lib/i18n";

// MapLibre touches `window`, so it only renders on the client.
const WardMap = dynamic(() => import("@/components/WardMap").then((m) => m.WardMap), { ssr: false });
const Legend = dynamic(() => import("@/components/WardMap").then((m) => m.Legend), { ssr: false });

type Tab = "heat" | "solar" | "assistant" | "signals" | "console";
const TABS: { id: Tab; label: Key }[] = [
  { id: "heat", label: "tabHeat" },
  { id: "solar", label: "tabSolar" },
  { id: "assistant", label: "tabAssistant" },
  { id: "signals", label: "tabSignals" },
  { id: "console", label: "tabConsole" },
];

const LAYER_LABELS: [keyof LayerState, Key][] = [
  ["dlst", "layerDlst"],
  ["hotspots", "layerHotspots"],
  ["facilities", "layerFacilities"],
  ["fire", "layerFire"],
  ["protectedAreas", "layerPa"],
];

export default function Home() {
  const { t, lang, setLang } = useI18n();
  const [tab, setTab] = useState<Tab>("heat");
  const [selected, setSelected] = useState<string | null>(null);
  const [roofs, setRoofs] = useState<RoofItem[] | null>(null);
  const [layers, setLayers] = useState<LayerState>({
    dlst: false,
    hotspots: true,
    facilities: false,
    fire: false,
    protectedAreas: false,
  });
  const [colorBy, setColorBy] = useState<ColorBy>("priority");

  const wards = useQuery({ queryKey: ["wards"], queryFn: api.wards });
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: api.forecast, retry: false });
  const facilities = useQuery({ queryKey: ["facilities"], queryFn: api.facilities, retry: false });
  const fire = useQuery({ queryKey: ["fire"], queryFn: api.fire, retry: false });
  const pas = useQuery({ queryKey: ["pas"], queryFn: api.protectedAreas, retry: false });

  const selectedWard = wards.data?.wards.find((w) => w.ward_id === selected) ?? null;
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

  const ranked = [...(wards.data?.wards ?? [])].sort((a, b) => (a.priority.rank ?? 99) - (b.priority.rank ?? 99));
  const pick = (id: string) => {
    setSelected(id);
    setRoofs(null);
  };
  const official = wards.data?.signals.official_warning;
  const dlstMeta = wards.data?.layers.dlst;

  return (
    <main>
      <header className="top">
        <div>
          <h1>{t("appTitle")}</h1>
          <p className="muted">{t("tagline")}</p>
        </div>
        <div className="lang" role="group" aria-label="Language">
          <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
            EN
          </button>
          <button type="button" aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>
            हिं
          </button>
        </div>
      </header>

      {official && (
        <aside className="banner official" role="status">
          <strong>
            {t("officialWarning")}: {official.level.toUpperCase()}
          </strong>{" "}
          · {official.issued_by} · {official.valid_until.slice(0, 10)} — {official.text}
        </aside>
      )}

      <nav className="tabs" role="tablist">
        {TABS.map(({ id, label }) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {t(label)}
          </button>
        ))}
      </nav>

      {tab === "heat" && (
        <div className="grid">
          <div className="col">
            {forecast.data && !["none", "unavailable"].includes(forecast.data.risk) && (
              <aside className="banner" role="status">
                <strong>
                  {t("heatDome")}: {forecast.data.risk}
                </strong>
                {forecast.data.first_date && ` · ${forecast.data.first_date}`}
                {forecast.data.duration_days && ` · ${forecast.data.duration_days} d`}
                {forecast.data.tmax_range_c && ` · ${forecast.data.tmax_range_c[0]}–${forecast.data.tmax_range_c[1]} °C`}
                <br />
                <span className="muted">{t("heatDomeNote")}</span>
              </aside>
            )}
            <p className="muted small">{t("lstNote")}</p>
            {wards.isLoading && <p>{t("loading")}</p>}
            {wards.error && (
              <p className="warn">
                {t("error")}: {wards.error.message}
              </p>
            )}
            {wards.data && wardGeo && (
              <>
                <fieldset className="layers">
                  <legend>{t("layers")}</legend>
                  {LAYER_LABELS.map(([key, label]) => (
                    <label key={key} className="check">
                      <input
                        type="checkbox"
                        checked={layers[key]}
                        disabled={key === "dlst" && !dlstMeta}
                        onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))}
                      />
                      {t(label)}
                    </label>
                  ))}
                  <label className="check">
                    {t("colorBy")}
                    <select value={colorBy} onChange={(e) => setColorBy(e.target.value as ColorBy)}>
                      <option value="priority">{t("byPriority")}</option>
                      <option value="degradation">{t("byDegradation")}</option>
                    </select>
                  </label>
                </fieldset>
                <WardMap
                  wards={wardGeo}
                  hotspots={wards.data.hotspots}
                  roofs={roofGeo}
                  facilities={facilities.data ?? null}
                  fire={fireGeo}
                  protectedAreas={paGeo}
                  tilesUrl={dlstMeta ? api.tilesUrl() : null}
                  layers={layers}
                  colorBy={colorBy}
                  wardCount={wards.data.wards.length}
                  selected={selected}
                  onSelect={pick}
                />
                <Legend title={colorBy === "priority" ? t("mapLegend") : t("byDegradation")} count={wards.data.wards.length} colorBy={colorBy} />
                {layers.dlst && dlstMeta && (
                  <p className="muted small">
                    {t("dlstLegend")} ({fmt(dlstMeta.vmin, 1)} → {fmt(dlstMeta.vmax, 1)} °C)
                  </p>
                )}
                {layers.fire && (
                  <p className="muted small">
                    {t("fireNote")} {wards.data.fire_as_of ? `(${wards.data.fire_as_of})` : ""}
                  </p>
                )}
                {layers.protectedAreas && pas.data?.areas.map((a) => (
                  <p key={a.pa_id} className="muted small">
                    {a.name}: {a.pressure} (HPI {a.hpi ?? "—"}). {t("habitat")}
                  </p>
                ))}
                <section className="card">
                  <h2>{t("ranking")}</h2>
                  <ol className="ranking">
                    {ranked.map((w) => (
                      <li key={w.ward_id}>
                        <button type="button" aria-pressed={w.ward_id === selected} onClick={() => pick(w.ward_id)}>
                          <span className="rk">{w.priority.rank ?? "—"}</span>
                          <span className="nm">{lang === "hi" ? w.name_hi : w.name}</span>
                          <span className="bar" aria-hidden="true">
                            <span style={{ width: `${Math.round((w.priority.priority ?? 0) * 100)}%` }} />
                          </span>
                          <span className="muted small">
                            {w.priority.rank_interval && `${w.priority.rank_interval[0]}–${w.priority.rank_interval[1]}`}
                            {w.mean_dlst_c && typeof w.mean_dlst_c.value === "number" && ` · ${fmt(w.mean_dlst_c.value, 1)} °C`}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ol>
                </section>
              </>
            )}
          </div>
          <div className="col">
            {selectedWard ? (
              <WardPanel ward={selectedWard} onRoofs={setRoofs} />
            ) : (
              <section className="card">
                <p className="muted">{t("selectWard")}</p>
              </section>
            )}
          </div>
        </div>
      )}

      {tab === "solar" && (
        <div className="narrow">
          <SolarCard />
        </div>
      )}
      {tab === "assistant" && (
        <div className="narrow">
          <ChatPanel wardId={selected} />
        </div>
      )}
      {tab === "signals" && <SignalsPanel wards={wards.data} />}
      {tab === "console" && <PlannerConsole wards={wards.data} selected={selected} />}

      <footer className="muted small">
        {t("disclaimer")} · {t("syntheticNote")}
      </footer>
    </main>
  );
}
