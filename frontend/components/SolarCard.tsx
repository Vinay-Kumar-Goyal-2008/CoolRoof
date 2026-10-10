"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api, type SolarRequest } from "@/lib/api";
import { fmt, useI18n } from "@/lib/i18n";
import { ClassTag } from "./Badge";

// Demo location (the synthetic city centre) and its synthetic DISCOM.
const DEMO = { lat: 18.52, lon: 73.86, state: "TEST", discom: "TEST-DISCOM" } as const;

export function SolarCard() {
  const { t, lang } = useI18n();
  const [area, setArea] = useState("70");
  const [units, setUnits] = useState("400");
  const [cost, setCost] = useState("180000");

  const build = (): SolarRequest => ({
    ...DEMO,
    roof_area_m2: Number(area) || undefined,
    avg_monthly_kwh: Number(units) || undefined,
    gross_cost_inr: Number(cost) || undefined,
  });
  const assess = useMutation({ mutationFn: () => api.assess(build()) });
  const pdf = useMutation({
    mutationFn: () => api.pdf(build(), lang),
    onSuccess: (r) => window.open(`/api${r.url}`, "_blank", "noopener"),
  });
  const r = assess.data;

  return (
    <section className="card">
      <h2>{t("solarTitle")}</h2>
      <form className="form" onSubmit={(e) => { e.preventDefault(); assess.mutate(); }}>
        <label>{t("roofArea")}
          <input inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)} required /></label>
        <label>{t("monthlyUnits")}
          <input inputMode="decimal" value={units} onChange={(e) => setUnits(e.target.value)} /></label>
        <label>{t("grossCost")}
          <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} /></label>
        <button type="submit" disabled={assess.isPending}>{assess.isPending ? t("loading") : t("check")}</button>
      </form>
      {assess.error && <p className="warn">{t("error")}: {assess.error.message}</p>}

      {r && (
        <div className="result">
          {r.system && (
            <>
              <h3>{t("systemSize")}</h3>
              <p className="big">{fmt(r.system.kw_recommended)} kW <ClassTag cls="ESTIMATE" /></p>
              <p className="muted">{t("generation")}: {fmt(r.system.generation_year1_kwh.low)}–{fmt(r.system.generation_year1_kwh.high)} kWh
                {" "}<ClassTag cls="ASSUMPTION" /></p>
            </>
          )}
          {r.subsidy && (
            <>
              <h3>{t("subsidy")}</h3>
              <p className="big">{lang === "hi" ? r.subsidy.amount.hi : r.subsidy.amount.en} <ClassTag cls="FACT" /></p>
              <p className="muted small">
                policy {r.subsidy.policy_version} · <a href={r.subsidy.source_url} target="_blank" rel="noreferrer">source</a>
                {" · "}hash {r.subsidy.record_hash} · top-up {r.subsidy.state_topup} · eligibility {r.subsidy.eligibility}
              </p>
            </>
          )}
          <h3>{t("payback")}</h3>
          {r.payback?.payback_simple_years ? (
            <p className="big">
              {fmt(r.payback.payback_simple_years.high, 1)}–{fmt(r.payback.payback_simple_years.low, 1)} {t("years")}{" "}
              <ClassTag cls="ESTIMATE" />
            </p>
          ) : (
            <p className="muted">{t("paybackNeed")} ({r.payback?.status})</p>
          )}
          {r.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
          <p className="muted small">{lang === "hi" ? r.disclaimer_hi : r.disclaimer_en}</p>
          <button type="button" onClick={() => pdf.mutate()} disabled={pdf.isPending}>{t("downloadPdf")}</button>
          {pdf.error && <p className="warn">{pdf.error.message}</p>}
        </div>
      )}
      <p className="muted small">{t("syntheticNote")}</p>
    </section>
  );
}
