"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, getStaff, setStaff, type Advisory, type WardsResponse } from "@/lib/api";
import { fmt, useI18n } from "@/lib/i18n";

/** Screen 11: planner console. Everything here calls staff-only API routes with the planner key. */
export function PlannerConsole({ wards, selected }: { wards: WardsResponse | undefined; selected: string | null }) {
  const { t } = useI18n();
  const [key, setKey] = useState("");
  const [actor, setActor] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const s = getStaff();
    setKey(s.key);
    setActor(s.actor);
    setSaved(!!s.key);
  }, []);

  return (
    <div className="col">
      <section className="card">
        <h2>{t("staffLogin")}</h2>
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            setStaff(key.trim(), actor.trim());
            setSaved(!!key.trim());
          }}
        >
          <label>
            {t("apiKey")}
            <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
          </label>
          <label>
            {t("yourName")}
            <input value={actor} maxLength={40} onChange={(e) => setActor(e.target.value)} />
          </label>
          <button type="submit">{t("saveKey")}</button>
        </form>
      </section>
      {saved && (
        <div className="grid">
          <div className="col">
            <PlanCard />
            <WarningCard />
            <ParamCard />
            <RunCard />
          </div>
          <div className="col">
            <AdvisoryCard wards={wards} selected={selected} />
            <DraftAlerts />
            <IncidentCard />
          </div>
        </div>
      )}
    </div>
  );
}

function PlanCard() {
  const { t } = useI18n();
  const [budget, setBudget] = useState("2000000");
  const plan = useMutation({ mutationFn: () => api.plan(Number(budget)) });
  const csv = plan.data?.csv;
  return (
    <section className="card">
      <h2>{t("planBudget")}</h2>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          plan.mutate();
        }}
      >
        <input aria-label={t("budget")} inputMode="numeric" value={budget} onChange={(e) => setBudget(e.target.value)} />
        <button type="submit" disabled={plan.isPending}>
          {t("makePlan")}
        </button>
      </form>
      {plan.error && <p className="warn small">{plan.error.message}</p>}
      {plan.data && (
        <>
          <pre className="json small">{JSON.stringify({ ...plan.data, csv: undefined }, null, 1)}</pre>
          {csv && (
            <a href={`data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`} download="cool-roof-plan.csv">
              {t("downloadCsv")}
            </a>
          )}
        </>
      )}
    </section>
  );
}

function WarningCard() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const now = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 16);
  const [level, setLevel] = useState("orange");
  const [from, setFrom] = useState(iso(now));
  const [until, setUntil] = useState(iso(new Date(now.getTime() + 3 * 86_400_000)));
  const [text, setText] = useState("");
  const list = useQuery({ queryKey: ["warnings"], queryFn: api.warnings, retry: false });
  const add = useMutation({
    mutationFn: () =>
      api.addWarning({
        level,
        issued_by: "IMD",
        valid_from: `${from}:00Z`,
        valid_until: `${until}:00Z`,
        text,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["warnings"] });
      void qc.invalidateQueries({ queryKey: ["wards"] });
    },
  });
  return (
    <section className="card">
      <h2>{t("warningEntry")}</h2>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <label>
          {t("level")}
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            {["yellow", "orange", "red"].map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </label>
        <label>
          {t("validFrom")}
          <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label>
          {t("validUntil")}
          <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} />
        </label>
        <label>
          {t("text")}
          <input value={text} maxLength={400} required onChange={(e) => setText(e.target.value)} />
        </label>
        <button type="submit" disabled={add.isPending}>
          {t("save")}
        </button>
      </form>
      {add.error && <p className="warn small">{add.error.message}</p>}
      {list.data?.active && (
        <p className="small">
          ✓ {list.data.active.level} · {list.data.active.valid_until.slice(0, 10)}
        </p>
      )}
    </section>
  );
}

function ParamCard() {
  const { t } = useI18n();
  const list = useQuery({ queryKey: ["nv-params"], queryFn: () => api.params(true), retry: false });
  const [id, setId] = useState("");
  const [value, setValue] = useState("");
  const [source, setSource] = useState("");
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.setParam(id, JSON.parse(value), "R", source),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["nv-params"] }),
  });
  return (
    <section className="card">
      <h2>Parameters to verify [NV]</h2>
      <ul className="small">
        {list.data?.params.map((p) => (
          <li key={p.id}>
            <button type="button" className="link" onClick={() => setId(p.id)}>
              {p.id}
            </button>{" "}
            <span className="muted">{p.unit ?? ""}</span>
          </li>
        ))}
      </ul>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <label>
          ID
          <input value={id} onChange={(e) => setId(e.target.value)} required />
        </label>
        <label>
          Value (JSON)
          <input value={value} onChange={(e) => setValue(e.target.value)} required placeholder="e.g. 120" />
        </label>
        <label>
          Source (required)
          <input value={source} onChange={(e) => setSource(e.target.value)} required minLength={3} />
        </label>
        <button type="submit" disabled={save.isPending}>
          {t("save")} (admin)
        </button>
      </form>
      {save.error && <p className="warn small">{save.error.message}</p>}
      {save.isSuccess && <p className="small">✓ saved — re-run the analysis to apply to roof ranking</p>}
    </section>
  );
}

function RunCard() {
  const { t } = useI18n();
  const [exec, setExec] = useState<string | null>(null);
  const start = useMutation({ mutationFn: api.runAnalysis, onSuccess: (r) => setExec(r.execution_id) });
  const state = useQuery({
    queryKey: ["analysis", exec],
    queryFn: () => api.analysisState(exec as string),
    enabled: !!exec,
    refetchInterval: (q) => (q.state.data?.state === "running" ? 3000 : false),
  });
  return (
    <section className="card">
      <h2>{t("rerun")}</h2>
      <button type="button" onClick={() => start.mutate()} disabled={start.isPending || state.data?.state === "running"}>
        {t("rerun")}
      </button>
      {start.error && <p className="warn small">{start.error.message}</p>}
      {state.data && (
        <p className="small">
          {state.data.state} {state.data.steps.join(" → ")} {state.data.error ?? ""}
        </p>
      )}
    </section>
  );
}

function AdvisoryCard({ wards, selected }: { wards: WardsResponse | undefined; selected: string | null }) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const [type, setType] = useState("heatwave_relay");
  const list = useQuery({ queryKey: ["staff-advisories"], queryFn: api.advisories, retry: false });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["staff-advisories"] });
    void qc.invalidateQueries({ queryKey: ["public-advisories"] });
  };
  const create = useMutation({
    mutationFn: () => api.createAdvisory(type, selected, type === "heatdome_forecast" ? "staff" : undefined),
    onSuccess: refresh,
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "publish" | "withdraw" }) =>
      api.advisoryAction(id, action),
    onSuccess: refresh,
  });
  return (
    <section className="card">
      <h2>{t("composeAdvisory")}</h2>
      <div className="row">
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="type">
          <option value="heatwave_relay">heatwave_relay (official)</option>
          <option value="heatdome_forecast">heatdome_forecast (staff)</option>
          <option value="exam_event">exam_event</option>
        </select>
        <button type="button" onClick={() => create.mutate()} disabled={create.isPending}>
          {t("composeAdvisory")}
        </button>
      </div>
      <p className="muted small">{selected ? `${selected}` : "city"}</p>
      {create.error && <p className="warn small">{create.error.message}</p>}
      {act.error && <p className="warn small">{act.error.message}</p>}
      {list.data?.advisories.map((a: Advisory) => (
        <article key={a.advisory_id} className="reco">
          <p>
            <span className="tier">{a.status}</span> <span className="tier">{a.audience}</span> {a.texts[lang]}
          </p>
          <p className="muted small">
            {a.type} · {a.created_by} · {a.valid_until.slice(0, 10)}
          </p>
          <div className="row">
            {a.status === "draft" && (
              <button type="button" onClick={() => act.mutate({ id: a.advisory_id, action: "approve" })}>
                {t("approve")}
              </button>
            )}
            {a.status === "approved" && (
              <button type="button" onClick={() => act.mutate({ id: a.advisory_id, action: "publish" })}>
                {t("publish")}
              </button>
            )}
            {["approved", "published"].includes(a.status) && (
              <button type="button" onClick={() => act.mutate({ id: a.advisory_id, action: "withdraw" })}>
                {t("withdraw")}
              </button>
            )}
          </div>
        </article>
      ))}
      {wards && <p className="muted small">{fmt(wards.wards.length)} wards</p>}
    </section>
  );
}

function DraftAlerts() {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const alerts = useQuery({ queryKey: ["staff-alerts"], queryFn: () => api.alerts(undefined, true), retry: false });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "withdraw" }) => api.alertAction(id, action),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["staff-alerts"] }),
  });
  return (
    <section className="card">
      <h2>{t("drafts")}</h2>
      {alerts.data?.drafts.length === 0 && <p className="muted small">—</p>}
      {alerts.data?.drafts.map((a) => (
        <article key={a.alert_id} className="reco">
          <p>
            <span className="tier">{a.severity}</span> {a.texts[lang] ?? a.texts.en}
          </p>
          <button type="button" onClick={() => act.mutate({ id: a.alert_id, action: "approve" })}>
            {t("approve")} + send
          </button>
        </article>
      ))}
      <h3>{t("activeAlerts")} (staff)</h3>
      {alerts.data?.alerts.map((a) => (
        <p key={a.alert_id} className="small">
          <span className="tier">{a.audience}</span> {a.texts[lang] ?? a.texts.en}
        </p>
      ))}
      {act.error && <p className="warn small">{act.error.message}</p>}
    </section>
  );
}

function IncidentCard() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [lat, setLat] = useState("18.5300");
  const [lon, setLon] = useState("73.8400");
  const [notes, setNotes] = useState("");
  const list = useQuery({ queryKey: ["incidents"], queryFn: api.incidents, retry: false });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["incidents"] });
    void qc.invalidateQueries({ queryKey: ["staff-alerts"] });
  };
  const log = useMutation({ mutationFn: () => api.logIncident(Number(lat), Number(lon), notes), onSuccess: refresh });
  const confirm = useMutation({ mutationFn: (id: string) => api.confirmIncident(id), onSuccess: refresh });
  return (
    <section className="card">
      <h2>{t("incidents")}</h2>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          log.mutate();
        }}
      >
        <label>
          {t("lat")}
          <input value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />
        </label>
        <label>
          {t("lon")}
          <input value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" />
        </label>
        <label>
          {t("notes")}
          <input value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button type="submit" disabled={log.isPending}>
          {t("logIncident")}
        </button>
      </form>
      {(log.error || confirm.error) && <p className="warn small">{(log.error ?? confirm.error)?.message}</p>}
      {list.data?.incidents.map((i) => (
        <article key={i.incident_id} className="reco">
          <p>
            <span className="tier">{i.status.replace("structure_fire_", "")}</span> {i.ward_id ?? "?"} ·{" "}
            {i.occurred_at.slice(0, 16)} · {i.reported_by}
          </p>
          <p className="muted small">
            {i.nearby.hospitals.map((h) => `${h.name} ${h.distance_m} m`).join(", ") || "no hospital within cover radius"}
          </p>
          {i.status === "structure_fire_reported" && (
            <button type="button" onClick={() => confirm.mutate(i.incident_id)}>
              {t("confirm")}
            </button>
          )}
        </article>
      ))}
    </section>
  );
}
