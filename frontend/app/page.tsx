"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { SolarCard } from "@/components/SolarCard";
import { WardPanel } from "@/components/WardPanel";
import { api, type RoofItem } from "@/lib/api";
import { fmt, useI18n } from "@/lib/i18n";

// MapLibre touches `window`, so it only renders on the client.
const WardMap = dynamic(() => import("@/components/WardMap").then((m) => m.WardMap), { ssr: false });
const Legend = dynamic(() => import("@/components/WardMap").then((m) => m.Legend), { ssr: false });

type Tab = "heat" | "solar" | "assistant";

export default function Home() {
  const { t, lang, setLang } = useI18n();
  const [tab, setTab] = useState<Tab>("heat");
  const [selected, setSelected] = useState<string | null>(null);
  const [roofs, setRoofs] = useState<RoofItem[] | null>(null);

  const wards = useQuery({ queryKey: ["wards"], queryFn: api.wards });
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: api.forecast, retry: false });

  const selectedWard = wards.data?.wards.find((w) => w.ward_id === selected) ?? null;
  const roofGeo = useMemo<GeoJSON.FeatureCollection | null>(() => roofs && {
    type: "FeatureCollection",
    features: roofs.map((r) => ({ type: "Feature", properties: { id: r.building_id }, geometry: r.geometry })),
  }, [roofs]);

  const ranked = [...(wards.data?.wards ?? [])].sort((a, b) => (a.priority.rank ?? 99) - (b.priority.rank ?? 99));
  const pick = (id: string) => { setSelected(id); setRoofs(null); };

  return (
    <main>
      <header className="top">
        <div>
          <h1>{t("appTitle")}</h1>
          <p className="muted">{t("tagline")}</p>
        </div>
        <div className="lang" role="group" aria-label="Language">
          <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
          <button type="button" aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>हिं</button>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {(["heat", "solar", "assistant"] as const).map((id) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {t(id === "heat" ? "tabHeat" : id === "solar" ? "tabSolar" : "tabAssistant")}
          </button>
        ))}
      </nav>

      {tab === "heat" && (
        <div className="grid">
          <div className="col">
            {forecast.data && forecast.data.risk !== "none" && (
              <aside className="banner" role="status">
                <strong>{t("heatDome")}: {forecast.data.risk}</strong>
                {forecast.data.first_date && ` · ${forecast.data.first_date}`}
                {forecast.data.duration_days && ` · ${forecast.data.duration_days} d`}
                {forecast.data.tmax_range_c && ` · ${forecast.data.tmax_range_c[0]}–${forecast.data.tmax_range_c[1]} °C`}
                <br /><span className="muted">{t("heatDomeNote")}</span>
              </aside>
            )}
            <p className="muted small">{t("lstNote")}</p>
            {wards.isLoading && <p>{t("loading")}</p>}
            {wards.error && <p className="warn">{t("error")}: {wards.error.message}</p>}
            {wards.data && (
              <>
                <WardMap wards={wards.data.geojson} hotspots={wards.data.hotspots} roofs={roofGeo}
                         wardCount={wards.data.wards.length} selected={selected} onSelect={pick} />
                <Legend title={t("mapLegend")} count={wards.data.wards.length} />
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
            {selectedWard ? <WardPanel ward={selectedWard} onRoofs={setRoofs} /> : (
              <section className="card"><p className="muted">{t("selectWard")}</p></section>
            )}
          </div>
        </div>
      )}

      {tab === "solar" && <div className="narrow"><SolarCard /></div>}
      {tab === "assistant" && <div className="narrow"><ChatPanel wardId={selected} /></div>}

      <footer className="muted small">{t("disclaimer")} · {t("syntheticNote")}</footer>
    </main>
  );
}
