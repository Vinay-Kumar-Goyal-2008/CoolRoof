"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";

import { api } from "@/lib/api";
import { meanDlst, totalExposed } from "@/lib/data";
import { fmt, useI18n } from "@/lib/i18n";
import { COPY } from "@/lib/landing-copy";
import { IconArrowRight, LogoMark } from "./Icons";
import { LangToggle } from "./Shell";

const RAMP = ["#fde725", "#7ad151", "#22a884", "#2a788e", "#414487", "#440154"];

type Ring = number[][];
function rings(g: GeoJSON.Geometry): Ring[] {
  if (g.type === "Polygon") return g.coordinates as Ring[];
  if (g.type === "MultiPolygon") return (g.coordinates as Ring[][]).flat();
  return [];
}

/** Real ward polygons from the API, projected to SVG and coloured by priority rank. */
function WardViz({ lang }: { lang: "en" | "hi" }) {
  const c = COPY[lang];
  const q = useQuery({ queryKey: ["wards"], queryFn: api.wards, retry: false });
  const shapes = useMemo(() => {
    if (!q.data) return null;
    const rank = new Map(q.data.wards.map((w) => [w.ward_id, w.priority.rank]));
    const names = new Map(q.data.wards.map((w) => [w.ward_id, lang === "hi" ? w.name_hi : w.name]));
    const feats = q.data.geojson.features;
    const pts = feats.flatMap((f) => rings(f.geometry).flat());
    if (!pts.length) return null;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const kx = Math.cos(((y0 + y1) / 2) * Math.PI / 180);
    const W = 520, scale = W / ((x1 - x0) * kx), H = (y1 - y0) * scale;
    const n = q.data.wards.length;
    return {
      W, H,
      paths: feats.map((f) => {
        const id = String(f.properties?.ward_id);
        const r = rank.get(id);
        const d = rings(f.geometry)
          .map((ring) => "M" + ring.map(([x, y]) => `${((x - x0) * kx * scale).toFixed(1)},${(H - (y - y0) * scale).toFixed(1)}`).join("L") + "Z")
          .join("");
        const fill = r ? RAMP[Math.min(RAMP.length - 1, Math.floor(((r - 1) / n) * RAMP.length))] : "#5a4a3c";
        return { id, d, fill, label: `${names.get(id) ?? id}${r ? ` · #${r}` : ""}` };
      }),
    };
  }, [q.data, lang]);

  return (
    <figure className="wardviz reveal d2" style={{ margin: 0 }}>
      <div className="vz-cap" style={{ marginTop: 0, marginBottom: 14 }}>
        <span className="label">{c.vizTitle}</span>
      </div>
      {shapes ? (
        <svg className="vz" viewBox={`0 0 ${shapes.W} ${shapes.H}`} role="img" aria-label={c.vizTitle}>
          {shapes.paths.map((p) => (
            <path key={p.id} d={p.d} fill={p.fill}><title>{p.label}</title></path>
          ))}
        </svg>
      ) : (
        <p className="muted" style={{ padding: "90px 10px", textAlign: "center" }}>{q.isLoading ? "…" : c.vizOffline}</p>
      )}
      <div className="vz-cap">
        <span className="ramp"><span>{c.vizFirst}</span><i /><span>{c.vizLast}</span></span>
      </div>
      <p className="vz-note">{c.vizNote}</p>
    </figure>
  );
}

export function Landing() {
  const { lang } = useI18n();
  const c = COPY[lang];
  const wards = useQuery({ queryKey: ["wards"], queryFn: api.wards, retry: false });
  const list = wards.data?.wards ?? [];
  const first = [...list].sort((a, b) => (a.priority.rank ?? 99) - (b.priority.rank ?? 99))[0];
  const dlst = meanDlst(list);

  return (
    <div className="land">
      <div className="lwrap">
        <header className="lnav">
          <Link href="/" className="brand" aria-label="CoolRoof">
            <LogoMark />
            <div><b>{lang === "hi" ? "कूलरूफ" : "COOLROOF"}</b></div>
          </Link>
          <nav className="links" aria-label="Sections">
            <a href="#features">{c.navFeatures}</a>
            <a href="#trust">{c.navTrust}</a>
            <a href="#officers">{c.navHow}</a>
          </nav>
          <div className="sp" />
          <LangToggle />
          <Link href="/app" className="btn btn-primary">{c.open}</Link>
        </header>

        <section className="lhero">
          <div className="reveal">
            <p className="eyebrow">{c.eyebrow}</p>
            <h1 className="display">{c.h1a}<em>{c.h1b}</em></h1>
            <p className="lead">{c.lead}</p>
            <div className="hero-actions">
              <Link href="/app" className="btn btn-primary btn-lg">{c.ctaPrimary}<IconArrowRight size={20} /></Link>
              <a href="#features" className="btn btn-ghost btn-lg">{c.ctaSecondary}</a>
            </div>
          </div>
          <WardViz lang={lang} />
        </section>

        <section className="strip" aria-label="Live figures">
          <div><span className="label">{c.stripWards}</span><span className="val num">{list.length ? fmt(list.length) : "—"}</span></div>
          <div><span className="label">{c.stripExposed}</span><span className="val num">{fmt(totalExposed(list))}</span></div>
          <div><span className="label">{c.stripDlst}</span><span className="val num">{dlst === null ? "—" : `${fmt(dlst, 1)} °C`}</span></div>
          <div><span className="label">{c.stripFirst}</span><span className="val" style={{ fontFamily: "var(--f-display)" }}>{first ? (lang === "hi" ? first.name_hi : first.name) : "—"}</span></div>
        </section>

        <section className="lsec" id="features">
          <div className="head">
            <h2>{c.featuresH}</h2>
            <p className="lead">{c.featuresLead}</p>
          </div>

          <div className="feat">
            <div>
              <h3>{c.f1h}</h3>
              <p>{c.f1p}</p>
              <ul>{c.f1l.map((x) => <li key={x}>{x}</li>)}</ul>
            </div>
            <div className="panel" aria-hidden="true">
              {(first ? [first] : []).concat(list.filter((w) => w !== first).sort((a, b) => (a.priority.rank ?? 99) - (b.priority.rank ?? 99)).slice(0, 3)).map((w) => (
                <div key={w.ward_id} className="rowline">
                  <span>{lang === "hi" ? w.name_hi : w.name}</span>
                  <span className="v num">#{w.priority.rank ?? "—"}</span>
                </div>
              ))}
              {!list.length && <p className="cap">{c.vizOffline}</p>}
              <p className="cap">{c.vizNote}</p>
            </div>
          </div>

          <div className="feat flip">
            <div>
              <h3>{c.f2h}</h3>
              <p>{c.f2p}</p>
              <ul>{c.f2l.map((x) => <li key={x}>{x}</li>)}</ul>
            </div>
            <div className="panel">
              {c.solarRows.map(([k, v]) => (
                <div key={k} className="rowline"><span>{k}</span><span className="v">{v}</span></div>
              ))}
              <p className="cap">{c.f2Cap}</p>
            </div>
          </div>

          <div className="feat" id="officers">
            <div>
              <h3>{c.f3h}</h3>
              <p>{c.f3p}</p>
              <ul>{c.f3l.map((x) => <li key={x}>{x}</li>)}</ul>
            </div>
            <div className="panel">
              {c.alertRows.map(([k, v]) => (
                <div key={k} className="rowline"><span>{k}</span><span className="muted small">{v}</span></div>
              ))}
            </div>
          </div>
        </section>

        <section className="lsec" id="trust">
          <div className="trust">
            <div>
              <h2>{c.trustH}</h2>
              <p className="lead">{c.trustLead}</p>
              <div className="flags" style={{ marginTop: 22, gap: 10 }} aria-hidden="true">
                {["measured", "derived", "estimated", "policy", "unavailable"].map((k) => <span key={k} className={`badge badge-${k}`}>{k}</span>)}
              </div>
            </div>
            <div className="rules">
              {c.rules.map(([h, p]) => (
                <div key={h}><b>{h}</b><span>{p}</span></div>
              ))}
            </div>
          </div>
        </section>

        <section className="cta">
          <div>
            <h2>{c.ctaH}</h2>
            <p className="lead">{c.ctaP}</p>
          </div>
          <Link href="/app" className="btn btn-primary btn-lg">{c.ctaPrimary}<IconArrowRight size={20} /></Link>
        </section>

        <footer className="lfoot">
          <span>{c.footA}</span>
          <span>{c.footB}</span>
        </footer>
      </div>
    </div>
  );
}
