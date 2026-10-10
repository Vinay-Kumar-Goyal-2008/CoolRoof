"use client";

import Link from "next/link";

import { IconArrow, IconBuilding, IconCross, IconFlame, IconGauge, IconPeople, IconPlus, IconSun, IconThermo, IconWarn } from "@/components/Icons";
import { meanDlst, totalExposed, useAppData } from "@/lib/data";
import { fmt, useI18n } from "@/lib/i18n";

export default function Overview() {
  const { t, lang } = useI18n();
  const { wards, ranked, forecast, alerts, facilities } = useAppData();
  const list = wards.data?.wards ?? [];
  const nameOf = (w: { name: string; name_hi: string }) => (lang === "hi" ? w.name_hi : w.name);
  const top = ranked[0];
  const risk = forecast.data?.risk;
  const hasSignal = !!risk && !["none", "unavailable"].includes(risk);
  const hottest = [...list]
    .filter((w) => typeof w.mean_dlst_c?.value === "number")
    .sort((a, b) => (b.mean_dlst_c!.value as number) - (a.mean_dlst_c!.value as number))
    .slice(0, 4);
  const kinds = new Map<string, number>();
  facilities.data?.features.forEach((f) => {
    const k = String(f.properties?.kind ?? "other");
    kinds.set(k, (kinds.get(k) ?? 0) + 1);
  });
  const facilityRows = [...kinds.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
  const maxFacility = Math.max(1, ...facilityRows.map(([, n]) => n));
  const feed = alerts.data?.alerts ?? [];

  return (
    <>
      <section className="hero">
        <div>
          <p className="eyebrow">{t("heroEyebrow")}</p>
          <h1 className="display">{t("heroA")}<em>{t("heroB")}</em></h1>
          <p className="lead">{t("heroLead")}</p>
        </div>
        <div className="hero-actions">
          <Link href="/app/solar" className="btn btn-ghost"><IconSun size={18} />{t("checkRoof")}</Link>
          <Link href="/app/heat" className="btn btn-primary"><IconPlus size={18} />{t("openHeat")}</Link>
        </div>
      </section>

      {wards.isLoading && <p className="muted">{t("loading")}</p>}
      {wards.error && <p className="warn">{t("error")}: {wards.error.message}. {t("noData")}</p>}

      <section className="kpis" aria-label="Key figures">
        <article className="card kpi">
          <div className="kpi-top"><span className="label">{t("kpiWards")}</span><span className="chipicon"><IconBuilding size={18} /></span></div>
          <div>
            <div className="val num">{list.length ? fmt(list.length) : "—"}</div>
            <p className="sub"><span className="dot" />{top ? `${t("highestPriority")}: ${nameOf(top)}` : "—"}</p>
          </div>
        </article>
        <article className="card kpi">
          <div className="kpi-top"><span className="label">{t("kpiExposed")}</span><span className="chipicon info"><IconPeople size={18} /></span></div>
          <div>
            <div className="val num">{fmt(totalExposed(list))}</div>
            <p className="sub"><span className="dot info" />{t("exposedSub")}</p>
          </div>
        </article>
        <article className="card kpi">
          <div className="kpi-top"><span className="label">{t("kpiDlst")}</span><span className="chipicon good"><IconGauge size={18} /></span></div>
          <div>
            <div className="val num">{meanDlst(list) === null ? "—" : `${fmt(meanDlst(list), 1)} °C`}</div>
            <p className="sub"><span className="dot good" />{t("dlstSub")}</p>
          </div>
        </article>
        <article className="card kpi">
          <div className="kpi-top"><span className="label">{t("kpiSignal")}</span><span className="chipicon bad"><IconThermo size={18} /></span></div>
          <div>
            <div className="val" style={{ textTransform: "capitalize" }}>{hasSignal ? risk : t("signalNone")}</div>
            <p className="sub"><span className="dot bad" />{t("heatDomeNote")}</p>
          </div>
        </article>
      </section>

      <section className="dash">
        <article className="card">
          <div className="card-head">
            <div><span className="label">{t("rankLabel")}</span><h2>{t("rankTitle")}</h2></div>
            <div className="legendrow"><span><span className="dot" /> {t("score")}</span></div>
          </div>
          <div className="toprank">
            {ranked.slice(0, 6).map((w) => (
              <Link key={w.ward_id} href={`/app/heat?ward=${w.ward_id}`}>
                <span className="rk">{w.priority.rank ?? "—"}</span>
                <span>{nameOf(w)}</span>
                <span className="bar" aria-hidden="true"><span style={{ width: `${Math.round((w.priority.priority ?? 0) * 100)}%` }} /></span>
                <span className="mono small muted">{w.priority.rank_interval ? `${w.priority.rank_interval[0]}–${w.priority.rank_interval[1]}` : ""}</span>
              </Link>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div><span className="label">{t("feedLabel")}</span><h2>{t("feedTitle")}</h2></div>
            <Link href="/app/alerts" className="view-all">{t("viewAll")} <IconArrow size={14} /></Link>
          </div>
          <div className="list">
            {feed.length === 0 && <div className="muted">{t("noAlerts")}</div>}
            {feed.slice(0, 4).map((a) => (
              <Link key={a.alert_id} href="/app/alerts">
                <span className="chipicon bad"><IconFlame size={18} /></span>
                <span className="grow"><span className="t">{a.texts[lang] ?? a.texts.en ?? a.type}</span><br /><span className="s mono">{a.severity} · {a.valid_until.slice(0, 10)}</span></span>
              </Link>
            ))}
          </div>
        </article>
      </section>

      <section className="dash2">
        <article className="card">
          <div className="card-head">
            <div><span className="label">{t("hotLabel")}</span><h2>{t("hotTitle")}</h2></div>
          </div>
          <div className="list">
            {hottest.map((w) => (
              <Link key={w.ward_id} href={`/app/heat?ward=${w.ward_id}`}>
                <span className="chipicon bad"><IconWarn size={18} /></span>
                <span className="grow"><span className="t">{nameOf(w)}</span><br /><span className="s">ΔLST {fmt(w.mean_dlst_c!.value as number, 1)} °C · {t("heatAbove")}</span></span>
                <span className="end"><IconArrow size={16} /></span>
              </Link>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div><span className="label">{t("readyLabel")}</span><h2>{t("readyTitle")}</h2></div>
            <span className="muted small mono">{fmt(facilities.data?.features.length ?? 0)} {t("facilitiesUnit")}</span>
          </div>
          <div className="list">
            {facilityRows.map(([k, n]) => (
              <div key={k}>
                <span className="chipicon good"><IconCross size={18} /></span>
                <span className="grow"><span className="t" style={{ textTransform: "capitalize" }}>{k.replaceAll("_", " ")}</span><br /><span className="s mono">{fmt(n)}</span></span>
                <span className="end"><span className="bar good mini-bar" aria-hidden="true"><span style={{ width: `${(n / maxFacility) * 100}%` }} /></span></span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section>
        <div className="sectionhead">
          <div><span className="label">{t("workLabel")}</span><h2>{t("workTitle")}</h2></div>
          <Link href="/app/heat" className="view-all">{t("viewHeat")} <IconArrow size={14} /></Link>
        </div>
        <div className="cards3">
          {ranked.slice(0, 3).map((w) => {
            const pct = Math.round((w.priority.priority ?? 0) * 100);
            return (
              <Link key={w.ward_id} href={`/app/heat?ward=${w.ward_id}`} className="card pcard">
                <div className="pt"><span className="tag">{t("rankN")} {w.priority.rank ?? "—"}</span><span className="mono small muted">{w.heat_type.type.replaceAll("_", " ")}</span></div>
                <div>
                  <h3>{nameOf(w)}</h3>
                  <p className="muted small" style={{ margin: "4px 0 0" }}>{fmt(w.exposed_population?.value as number | undefined)} {t("exposedShort")}</p>
                </div>
                <div>
                  <div className="pp"><span>{t("score")}</span><b>{pct}%</b></div>
                  <span className="bar" aria-hidden="true"><span style={{ width: `${pct}%` }} /></span>
                </div>
                <div className="pf"><span>{w.mean_dlst_c ? `ΔLST ${fmt(w.mean_dlst_c.value as number, 1)} °C` : "ΔLST —"}</span><span>{w.data_quality.flags.length} {w.data_quality.flags.length === 1 ? "flag" : "flags"}</span></div>
              </Link>
            );
          })}
        </div>
      </section>
    </>
  );
}
