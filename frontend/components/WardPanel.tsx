"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, api, type Driver, type RoofItem, type WardSummary } from "@/lib/api";
import {
  getDelhiDrivers,
  getDelhiHeatType,
  getDelhiReadiness,
  getDelhiRecommendations,
  getDelhiRoofs,
  getDelhiSoil,
} from "@/lib/delhi_data";
import { fmt, useI18n } from "@/lib/i18n";
import { Badge } from "./Badge";

/** True when the ward belongs to the offline Delhi dataset (no backend needed). */
const isDelhi = (wardId: string) => wardId.startsWith("DEL-");

export function WardPanel({ ward, onRoofs }: { ward: WardSummary;
                                                onRoofs: (roofs: RoofItem[] | null) => void }) {
  const { t, lang } = useI18n();
  const delhi = isDelhi(ward.ward_id);

  const type = useQuery({
    queryKey: ["type", ward.ward_id],
    queryFn: () =>
      delhi ? Promise.resolve(getDelhiHeatType(ward.ward_id)) : api.heatType(ward.ward_id),
  });

  const recs = useQuery({
    queryKey: ["recs", ward.ward_id, lang],
    queryFn: () =>
      delhi
        ? Promise.resolve(getDelhiRecommendations(ward.ward_id, lang))
        : api.recommendations(ward.ward_id, lang),
  });

  const roofs = useQuery({
    queryKey: ["roofs", ward.ward_id],
    queryFn: async () => {
      const r = delhi ? getDelhiRoofs(ward.ward_id) : await api.roofs(ward.ward_id);
      onRoofs(r.roofs);
      return r;
    },
    retry: false,
  });

  const drivers = useQuery({
    queryKey: ["drivers", ward.ward_id],
    queryFn: () =>
      delhi ? Promise.resolve(getDelhiDrivers(ward.ward_id)) : api.drivers(ward.ward_id),
    retry: false,
  });

  const ready = useQuery({
    queryKey: ["ready", ward.ward_id, lang],
    queryFn: () =>
      delhi
        ? Promise.resolve(getDelhiReadiness(ward.ward_id, lang))
        : api.readiness(ward.ward_id, lang),
    retry: false,
  });

  const soil = useQuery({
    queryKey: ["soil", ward.ward_id],
    queryFn: () =>
      delhi ? Promise.resolve(getDelhiSoil(ward.ward_id)) : api.soil(ward.ward_id),
    retry: false,
  });

  const name = lang === "hi" ? ward.name_hi : ward.name;
  const p = ward.priority;

  return (
    <section className="card" aria-live="polite">
      <h2>{name}</h2>
      <p className="muted">
        {t("rank")} <strong>{p.rank ?? "—"}</strong>
        {p.rank_interval && ` (${t("rankRange")} ${p.rank_interval[0]}–${p.rank_interval[1]})`}
      </p>
      <dl className="facts">
        <dt>ΔLST</dt>
        <dd><Badge env={ward.mean_dlst_c} unit="°C" /> <span className="muted">{t("heatAbove")}</span></dd>
        <dt>{t("people")}</dt>
        <dd><Badge env={ward.population} digits={0} /> · <Badge env={ward.exposed_population} digits={0} />{" "}
          <span className="muted">{t("exposed")}</span></dd>
      </dl>
      {ward.data_quality.flags.length > 0 && (
        <p className="flags">{ward.data_quality.flags.map((f) => <span key={f} className="flag">{f}</span>)}</p>
      )}

      <h3>{t("heatType")}: {type.data ? type.data.type.replaceAll("_", " ") : "…"}</h3>
      {type.isLoading && <p className="muted small">{t("loading")}</p>}
      {type.data?.brief.means && (
        <ul className="brief">
          <li><strong>{t("whatItMeans")}:</strong> {type.data.brief.means}</li>
          {!!type.data.brief.check?.length && <li><strong>{t("toCheck")}:</strong> {type.data.brief.check.join("; ")}</li>}
          {!!type.data.brief.departments?.length && <li><strong>{t("departments")}:</strong> {type.data.brief.departments.join(", ")}</li>}
        </ul>
      )}

      {drivers.data && (
        <>
          <h3>{t("drivers")}</h3>
          <DriverBars drivers={drivers.data.drivers.slice(0, 5)} lang={lang} />
          <p className="muted small">
            {t("driversNote")}
            {drivers.data.model_card.gbm_spatial_cv_r2 !== null &&
              ` R² (spatial CV) ${fmt(drivers.data.model_card.gbm_spatial_cv_r2, 2)}.`}
          </p>
        </>
      )}
      {drivers.error instanceof ApiError && (
        <p className="muted small">{t("drivers")}: {drivers.error.message}</p>
      )}

      <h3>{t("recommendations")}</h3>
      {recs.isLoading && <p className="muted">{t("loading")}</p>}
      {recs.data?.recommendations.map((r) => (
        <article key={r.id} className="reco">
          <p><span className="tier">T{r.tier}</span> {r.text}</p>
          {r.options && <p className="muted">{r.options.map((o) => `${o.name} (${o.cost_band})`).join(" · ")}</p>}
          <p className="muted small">
            {t("evidence")}: {r.evidence.map((e) => `${e.id} [${e.grade}]`).join(", ")}
            {r.caveats[0] && ` — ${r.caveats[0]}`}
          </p>
        </article>
      ))}
      {!!recs.data?.not_evaluated.length && (
        <p className="muted small">{t("notEvaluated")}: {recs.data.not_evaluated.map((n) => n.id).join(", ")}</p>
      )}

      {ready.data && (
        <>
          <h3>{t("readiness")}</h3>
          <p className="muted small">
            {fmt(ready.data.facilities.hospital_count)} {t("hospitals")} · {fmt(ready.data.facilities.school_count)} {t("schools")} ·{" "}
            {fmt(ready.data.facilities.cooling_point_count)} {t("coolingPoints")}
            {ready.data.facilities.nearest_hospital_m !== null && ` · ${t("nearestHospital")} ${fmt(ready.data.facilities.nearest_hospital_m)} m`}
          </p>
          {ready.data.prompts.length === 0 && <p className="muted small">{t("noPrompts")}</p>}
          {ready.data.prompts.map((pr) => (
            <p key={pr.id} className="reco small"><span className="tier">{pr.id}</span> {pr.text} <span className="muted">({pr.audience})</span></p>
          ))}
          <p className="muted small">{ready.data.note}</p>
        </>
      )}

      {soil.data && (
        <>
          <h3>{t("land")}</h3>
          <p>
            {t("signalLabel")}: <strong>{soil.data.degradation_signal.replaceAll("_", " ")}</strong>
            {soil.data.stability_share !== null && <span className="muted small"> · {fmt(soil.data.stability_share * 100)}% {t("stability")}</span>}
          </p>
          {!!soil.data.series.length && <Sparkline values={soil.data.series.map((r) => r.ndvi)} label="NDVI" />}
          <p className="muted small">{soil.data.label}{soil.data.caveats.length ? ` · ${soil.data.caveats.join("; ")}` : ""}</p>
        </>
      )}

      {typeof ward.fire_events_30d === "number" && ward.fire_events_30d > 0 && (
        <p className="warn small">{ward.fire_events_30d} {t("layerFire")}. {t("fireNote")}</p>
      )}

      <h3>{t("topRoofs")}</h3>
      {roofs.isLoading && <p className="muted small">{t("loading")}</p>}
      {roofs.error instanceof ApiError && <p className="warn">{t("roofsWithheld")}: {roofs.error.message}</p>}
      {roofs.data && (
        <>
          <ol className="roofs">
            {roofs.data.roofs.map((r) => (
              <li key={r.building_id}>
                <span className="mono">{r.building_id.slice(0, 9)}</span> · {fmt(r.area_m2)} m² ·{" "}
                {fmt(r.assessment.protected_people.low, 1)}–{fmt(r.assessment.protected_people.high, 1)} {t("protected")}
              </li>
            ))}
          </ol>
          {roofs.data.roofs[0]?.assessment.cost_inr === null && <p className="muted small">{t("costUnavailable")}</p>}
        </>
      )}
    </section>
  );
}

function DriverBars({ drivers, lang }: { drivers: Driver[]; lang: "en" | "hi" }) {
  const { t } = useI18n();
  const max = Math.max(...drivers.map((d) => Math.max(Math.abs(d.ci_low), Math.abs(d.ci_high), Math.abs(d.contribution_c))), 0.1);
  return (
    <ul className="drivers">
      {drivers.map((d) => {
        const pct = (v: number) => 50 + (v / max) * 50;
        return (
          <li key={d.feature}>
            <span className="dlabel">
              {d.label[lang]} <span className="muted small">({t(d.direction)}{d.stable ? "" : `, ${t("unstable")}`})</span>
            </span>
            <svg viewBox="0 0 100 10" className="dbar" role="img"
                 aria-label={`${d.label[lang]} ${fmt(d.contribution_c, 2)} °C`}>
              <line x1="50" y1="0" x2="50" y2="10" stroke="currentColor" strokeWidth="0.4" opacity="0.5" />
              <rect x={Math.min(50, pct(d.contribution_c))} y="2" height="6"
                    width={Math.abs(pct(d.contribution_c) - 50)}
                    fill={d.contribution_c > 0 ? "#d7301f" : "#2a788e"} />
              <line x1={pct(d.ci_low)} y1="5" x2={pct(d.ci_high)} y2="5" stroke="currentColor" strokeWidth="0.8" />
            </svg>
            <span className="mono small">{fmt(d.contribution_c, 2)} °C</span>
          </li>
        );
      })}
    </ul>
  );
}

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - lo) / span) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" className="spark" role="img" aria-label={`${label} ${fmt(values[0], 2)} → ${fmt(values[values.length - 1], 2)}`}>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
