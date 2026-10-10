"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, api, type RoofItem, type WardSummary } from "@/lib/api";
import { fmt, useI18n } from "@/lib/i18n";
import { Badge } from "./Badge";

export function WardPanel({ ward, onRoofs }: { ward: WardSummary;
                                                onRoofs: (roofs: RoofItem[] | null) => void }) {
  const { t, lang } = useI18n();
  const type = useQuery({ queryKey: ["type", ward.ward_id], queryFn: () => api.heatType(ward.ward_id) });
  const recs = useQuery({ queryKey: ["recs", ward.ward_id, lang],
                          queryFn: () => api.recommendations(ward.ward_id, lang) });
  const roofs = useQuery({
    queryKey: ["roofs", ward.ward_id],
    queryFn: async () => { const r = await api.roofs(ward.ward_id); onRoofs(r.roofs); return r; },
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
      {type.data?.brief.means && (
        <ul className="brief">
          <li><strong>{t("whatItMeans")}:</strong> {type.data.brief.means}</li>
          {!!type.data.brief.check?.length && <li><strong>{t("toCheck")}:</strong> {type.data.brief.check.join("; ")}</li>}
          {!!type.data.brief.departments?.length && <li><strong>{t("departments")}:</strong> {type.data.brief.departments.join(", ")}</li>}
        </ul>
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

      <h3>{t("topRoofs")}</h3>
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
