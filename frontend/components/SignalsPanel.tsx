"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Advisory, type WardsResponse } from "@/lib/api";
import { fmt, useI18n } from "@/lib/i18n";

/** Screen 9: heat-dome forecast signal, official warning, public alerts and advisories (with audio). */
export function SignalsPanel({ wards }: { wards: WardsResponse | undefined }) {
  const { t, lang } = useI18n();
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: api.forecast, retry: false });
  const history = useQuery({ queryKey: ["forecast-history"], queryFn: api.forecastHistory, retry: false });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts(), refetchInterval: 60_000 });
  const advisories = useQuery({ queryKey: ["public-advisories"], queryFn: api.publicAdvisories });
  const official = wards?.signals.official_warning ?? null;
  const f = forecast.data;

  return (
    <div className="grid">
      <div className="col">
        {official && (
          <aside className="banner official" role="status">
            <strong>
              {t("officialWarning")}: {official.level.toUpperCase()}
            </strong>{" "}
            · {official.issued_by} · {official.valid_from.slice(0, 10)} → {official.valid_until.slice(0, 10)}
            <br />
            {official.text}
          </aside>
        )}

        <section className="card">
          <h2>{t("forecastPanel")}</h2>
          {forecast.isLoading && <p>{t("loading")}</p>}
          {forecast.error && <p className="muted">{forecast.error.message}</p>}
          {f && (
            <>
              <p className="big">{f.risk}</p>
              <dl className="facts">
                <dt>{t("eventProbability")}</dt>
                <dd>{f.p_event === null ? "—" : `${fmt(f.p_event * 100)}%`}</dd>
                <dt>{t("firstDay")}</dt>
                <dd>{f.first_date ?? "—"}</dd>
                <dt>{t("duration")}</dt>
                <dd>{f.duration_days ?? "—"}</dd>
                <dt>{t("tmaxRange")}</dt>
                <dd>{f.tmax_range_c ? `${fmt(f.tmax_range_c[0], 1)}–${fmt(f.tmax_range_c[1], 1)}` : "—"}</dd>
              </dl>
              {f.criteria_mode === "temperature_only" && <p className="warn small">{t("tempOnly")}</p>}
              {f.imd_style?.meets && (
                <p className="small">
                  {t("imdStyle")} ({fmt(f.imd_style.member_share * 100)}%).
                </p>
              )}
              <p className="muted small">
                {lang === "hi" ? f.label_hi : f.label_en} · {f.source}
                {f.issued_at ? ` · ${f.issued_at.slice(0, 16)}` : ""}
              </p>
            </>
          )}
          {!!history.data?.forecasts.length && (
            <p className="muted small">
              {history.data.forecasts
                .slice(0, 6)
                .map((h) => `${(h.issued_at ?? "").slice(5, 10)}: ${h.risk}`)
                .join(" · ")}
            </p>
          )}
        </section>

        <section className="card">
          <h2>{t("activeAlerts")}</h2>
          {alerts.data && alerts.data.alerts.length === 0 && <p className="muted">{t("noAlerts")}</p>}
          {alerts.data?.alerts.map((a) => (
            <article key={a.alert_id} className={`alert sev-${a.severity}`}>
              <p>
                <span className="tier">{a.severity}</span> {a.texts[lang] ?? a.texts.en}
              </p>
              <p className="muted small">
                {a.type} · {a.valid_until.slice(0, 10)}
              </p>
            </article>
          ))}
        </section>
      </div>

      <div className="col">
        <section className="card">
          <h2>{t("advisories")}</h2>
          {advisories.data?.advisories.length === 0 && <p className="muted">{t("noAlerts")}</p>}
          {advisories.data?.advisories.map((a) => <AdvisoryCard key={a.advisory_id} a={a} />)}
        </section>
        <Subscribe wards={wards} />
      </div>
    </div>
  );
}

function AdvisoryCard({ a }: { a: Advisory }) {
  const { t, lang } = useI18n();
  const audio = useMutation({ mutationFn: () => api.tts(a.advisory_id, lang) });
  const url = audio.data?.audio_url;
  return (
    <article className="reco">
      <p>{a.texts[lang]}</p>
      <p className="muted small">
        {a.ward_id ?? "city"} · {a.valid_until.slice(0, 10)}
      </p>
      <button type="button" onClick={() => audio.mutate()} disabled={audio.isPending}>
        {audio.isPending ? t("loading") : `🔊 ${t("listen")}`}
      </button>
      {url && <audio controls src={`/api${url}`} aria-label={t("listen")} />}
      {audio.data && !url && <p className="warn small">{t("audioFallback")}</p>}
      {audio.error && <p className="warn small">{audio.error.message}</p>}
    </article>
  );
}

function Subscribe({ wards }: { wards: WardsResponse | undefined }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [ward, setWard] = useState("");
  const sub = useMutation({
    mutationFn: () => api.subscribe(email, "email", ["en", "hi"], ward ? [ward] : undefined),
  });
  return (
    <section className="card">
      <h2>{t("subscribe")}</h2>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          sub.mutate();
        }}
      >
        <label>
          {t("email")}
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Ward
          <select value={ward} onChange={(e) => setWard(e.target.value)}>
            <option value="">—</option>
            {wards?.wards.map((w) => (
              <option key={w.ward_id} value={w.ward_id}>
                {w.ward_id} {w.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={sub.isPending}>
          {t("subscribe")}
        </button>
      </form>
      {sub.isSuccess && <p className="small">{t("subscribed")}</p>}
      {sub.error && <p className="warn small">{sub.error.message}</p>}
    </section>
  );
}
