"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import type { LayerState } from "@/components/WardMap";
import { WardPanel } from "@/components/WardPanel";
import { api } from "@/lib/api";
import { useAppData } from "@/lib/data";
import { fmt, useI18n, type Key } from "@/lib/i18n";

// MapLibre touches `window`, so it only renders on the client.
const WardMap = dynamic(() => import("@/components/WardMap").then((m) => m.WardMap), { ssr: false });
const Legend = dynamic(() => import("@/components/WardMap").then((m) => m.Legend), { ssr: false });

const LAYER_LABELS: [keyof LayerState, Key][] = [
  ["dlst", "layerDlst"],
  ["hotspots", "layerHotspots"],
  ["facilities", "layerFacilities"],
  ["fire", "layerFire"],
  ["protectedAreas", "layerPa"],
];

function Heat() {
  const { t, lang } = useI18n();
  const d = useAppData();
  const { wards, forecast, pas, ranked, selected, selectedWard, pick, layers, setLayers, colorBy, setColorBy } = d;
  const dlstMeta = wards.data?.layers.dlst;
  const wantWard = useSearchParams().get("ward");

  useEffect(() => {
    if (wantWard && wantWard !== selected) pick(wantWard);
    // run once per deep link
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantWard]);

  return (
    <>
      <header className="pagehead">
        <h1 className="display">{t("pageHeat")}</h1>
        <p className="lead">{t("lstNote")}</p>
      </header>

      <div className="split">
        <div className="col">
          {forecast.data && !["none", "unavailable"].includes(forecast.data.risk) && (
            <aside className="banner" role="status">
              <strong>{t("heatDome")}: {forecast.data.risk}</strong>
              {forecast.data.first_date && ` · ${forecast.data.first_date}`}
              {forecast.data.duration_days && ` · ${forecast.data.duration_days} d`}
              {forecast.data.tmax_range_c && ` · ${forecast.data.tmax_range_c[0]}–${forecast.data.tmax_range_c[1]} °C`}
              <br /><span className="muted">{t("heatDomeNote")}</span>
            </aside>
          )}
          {wards.isLoading && <p>{t("loading")}</p>}
          {wards.error && <p className="warn">{t("error")}: {wards.error.message}</p>}
          {wards.data && d.wardGeo && (
            <>
              <fieldset className="layers">
                <legend>{t("layers")}</legend>
                {LAYER_LABELS.map(([key, label]) => (
                  <label key={key} className="check">
                    <input type="checkbox" checked={layers[key]} disabled={key === "dlst" && !dlstMeta}
                      onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))} />
                    {t(label)}
                  </label>
                ))}
                <label className="check">
                  {t("colorBy")}
                  <select value={colorBy} onChange={(e) => setColorBy(e.target.value as "priority" | "degradation")}>
                    <option value="priority">{t("byPriority")}</option>
                    <option value="degradation">{t("byDegradation")}</option>
                  </select>
                </label>
              </fieldset>
              <WardMap
                wards={d.wardGeo} hotspots={wards.data.hotspots} roofs={d.roofGeo}
                facilities={d.facilities.data ?? null} fire={d.fireGeo} protectedAreas={d.paGeo}
                tilesUrl={dlstMeta ? api.tilesUrl() : null} layers={layers} colorBy={colorBy}
                wardCount={wards.data.wards.length} selected={selected} onSelect={pick}
              />
              <Legend title={colorBy === "priority" ? t("mapLegend") : t("byDegradation")} count={wards.data.wards.length} colorBy={colorBy} />
              {layers.dlst && dlstMeta && (
                <p className="muted small">{t("dlstLegend")} ({fmt(dlstMeta.vmin, 1)} → {fmt(dlstMeta.vmax, 1)} °C)</p>
              )}
              {layers.fire && (
                <p className="muted small">{t("fireNote")} {wards.data.fire_as_of ? `(${wards.data.fire_as_of})` : ""}</p>
              )}
              {layers.protectedAreas && pas.data?.areas.map((a) => (
                <p key={a.pa_id} className="muted small">{a.name}: {a.pressure} (HPI {a.hpi ?? "—"}). {t("habitat")}</p>
              ))}
              <section className="card">
                <h2>{t("ranking")}</h2>
                <ol className="ranking" style={{ marginTop: 12 }}>
                  {ranked.map((w) => (
                    <li key={w.ward_id}>
                      <button type="button" aria-pressed={w.ward_id === selected} onClick={() => pick(w.ward_id)}>
                        <span className="rk">{w.priority.rank ?? "—"}</span>
                        <span className="nm">{lang === "hi" ? w.name_hi : w.name}</span>
                        <span className="bar" aria-hidden="true"><span style={{ width: `${Math.round((w.priority.priority ?? 0) * 100)}%` }} /></span>
                        <span className="muted small mono">
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
            <WardPanel ward={selectedWard} onRoofs={d.setRoofs} />
          ) : (
            <section className="card"><p className="muted">{t("selectWard")}</p></section>
          )}
        </div>
      </div>
    </>
  );
}

export default function HeatPage() {
  return (
    <Suspense fallback={null}>
      <Heat />
    </Suspense>
  );
}
