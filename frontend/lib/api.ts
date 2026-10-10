/** Typed client for the CoolRoof API (proxied through Next.js at /api). */

export type ValueClass =
  | "measured" | "derived" | "estimated" | "policy" | "user" | "unavailable" | "stale";

export interface Envelope {
  value: number | string | null;
  class: ValueClass;
  source: string;
  observed?: string;
  processed?: string;
  resolution_m?: number;
  confidence?: number;
  reason?: string;
  assumptions?: string[];
}

export interface Range3 { low: number; base: number; high: number }

export interface WardSummary {
  ward_id: string;
  name: string;
  name_hi: string;
  priority: {
    priority: number | null;
    rank: number | null;
    rank_interval: [number, number] | null;
    top_k_share: number | null;
    components: Record<string, number | null>;
    score_confidence: number;
    flags: string[];
    unscored_reason: string | null;
  };
  heat_type: { type: string; confidence: number | null };
  degradation_signal?: string | null;
  habitat_pressure_max?: string | null;
  fire_events_30d?: number | null;
  hospital_count?: number | null;
  nearest_hospital_m?: number | null;
  heatdome_risk?: string | null;
  mean_dlst_c?: Envelope;
  population?: Envelope;
  exposed_population?: Envelope;
  data_quality: { flags: string[]; context_confidence: number; missing: string[] };
}

export interface WardsResponse {
  wards: WardSummary[];
  geojson: GeoJSON.FeatureCollection;
  hotspots: GeoJSON.FeatureCollection | null;
  normalisation: string;
  scenes: { id: string; date: string; valid_pixel_pct: number }[];
  layers: Record<string, { key?: string; vmin?: number; vmax?: number; bounds?: number[] }>;
  fire_as_of: string | null;
  signals: Signals;
}

export interface OfficialWarning {
  warning_id: string;
  level: string;
  issued_by: string;
  valid_from: string;
  valid_until: string;
  text: string;
  source_url?: string | null;
}

export interface Signals {
  official_warning: OfficialWarning | null;
  forecast_risk: string;
  active: boolean;
}

export interface Driver {
  feature: string;
  label: { en: string; hi: string };
  contribution_c: number;
  direction: "warmer" | "cooler";
  ci_low: number;
  ci_high: number;
  stable: boolean;
}

export interface FireEvent {
  event_id: string;
  lat: number;
  lon: number;
  acq_date: string;
  acq_time: string;
  fire_class: string;
  confidence: string;
  frp_mw: number;
  alert: boolean;
  severity: string | null;
  ward_id: string | null;
  instrument: string;
}

export interface PaPressure {
  pa_id: string;
  name: string;
  hpi: number | null;
  pressure: string;
  previous_pressure: string | null;
  indicators: Record<string, { value: number; pct: number; significant: boolean; basis: string }>;
  warnings: { code: string; message: string }[];
  disclaimer: string;
}

export interface Alert {
  alert_id: string;
  type: string;
  severity: string;
  audience: string;
  status: string;
  texts: Record<string, string>;
  valid_until: string;
  ward_id: string | null;
}

export interface Advisory {
  advisory_id: string;
  type: string;
  audience: string;
  status: string;
  ward_id: string | null;
  texts: { en: string; hi: string };
  valid_until: string;
  created_by: string;
  approvals: { by: string }[];
}

export interface Incident {
  incident_id: string;
  lat: number;
  lon: number;
  occurred_at: string;
  status: string;
  ward_id: string | null;
  reported_by: string;
  confirmed_by: string | null;
  notes: string;
  nearby: { hospitals: { name: string; distance_m: number }[]; schools: { name: string }[] };
}

export interface Readiness {
  facilities: {
    hospital_count: number | null;
    school_count: number | null;
    cooling_point_count: number | null;
    nearest_hospital_m: number | null;
    facilities_per_10k_exposed: number | null;
  };
  prompts: { id: string; audience: string; text: string }[];
  note: string;
}

export interface SoilInfo {
  degradation_signal: string;
  stability_share: number | null;
  caveats: string[];
  label: string;
  trends: Record<
    string,
    { slope_per_year: number | null; p_value: number | null; trend: string; significant: boolean; adverse: boolean } | null
  >;
  series: { year: number; ndvi: number; bsi: number; lst_c: number }[];
}

export interface RoofItem {
  building_id: string;
  rank: number;
  area_m2: number;
  geometry: GeoJSON.Geometry;
  assessment: {
    protected_people: Range3;
    benefit: Range3;
    cost_inr: Range3 | null;
    dt_neighbourhood_c: Range3 | null;
    unavailable: Record<string, string[]>;
    heat_weight_c: number | null;
  };
}

export interface Recommendation {
  id: string;
  intervention: string;
  text: string;
  tier: number;
  evidence_grade: string;
  evidence: { id: string; title: string; url: string | null; grade: string }[];
  caveats: string[];
  options?: { id: string; name: string; cost_band: string }[];
}

export interface SolarRequest {
  lat: number;
  lon: number;
  state: string;
  discom: string;
  roof_area_m2?: number;
  avg_monthly_kwh?: number;
  gross_cost_inr?: number;
  roof_polygon?: GeoJSON.Polygon;
}

export interface DisplayField { value: number; class: string; en: string; hi: string }

export interface SolarResult {
  status: "complete" | "partial";
  missing: string[];
  next_questions: string[];
  warnings: string[];
  system: { kw_recommended: number; limiting_factor: string;
            generation_year1_kwh: Range3; assumptions: string[] } | null;
  subsidy: { amount: DisplayField; policy_version: string; effective_date: string;
             source_url: string; record_hash: string; state_topup: string;
             eligibility: string } | null;
  payback: { status: string; payback_simple_years?: Range3; net_cost_inr?: number;
             tariff_synthetic?: boolean } | null;
  disclaimer_en: string;
  disclaimer_hi: string;
}

export interface ChatReply {
  reply: string;
  citations: { source_url: string; effective_date: string }[];
  tool_calls: string[];
  needs: string[];
  pdf_url: string | null;
  lang: "en" | "hi";
  grounded: boolean;
  fallback_used: boolean;
}

export interface Forecast {
  risk: string;
  p_event: number | null;
  first_date: string | null;
  duration_days: number | null;
  tmax_range_c: [number, number] | null;
  label_en: string;
  label_hi: string;
}

export interface ForecastFull extends Forecast {
  low_confidence: boolean;
  criteria_mode: string;
  source: string;
  issued_at: string | null;
  imd_style: { meets: boolean; member_share: number; label: string } | null;
}

export class ApiError extends Error {
  constructor(public code: number, message: string) {
    super(message);
  }
}

const CITY = process.env.NEXT_PUBLIC_CITY ?? "mini_city";

// Planner key: kept only for this browser tab (sessionStorage), never persisted.
export function getStaff(): { key: string; actor: string } {
  try {
    return {
      key: window.sessionStorage.getItem("coolroof-key") ?? "",
      actor: window.sessionStorage.getItem("coolroof-actor") ?? "",
    };
  } catch {
    return { key: "", actor: "" };
  }
}
export function setStaff(key: string, actor: string): void {
  try {
    window.sessionStorage.setItem("coolroof-key", key);
    window.sessionStorage.setItem("coolroof-actor", actor);
  } catch {
    /* storage unavailable */
  }
}

async function call<T>(path: string, init?: RequestInit, staff = false): Promise<T> {
  const auth: Record<string, string> = {};
  if (staff) {
    const { key, actor } = getStaff();
    if (key) auth["X-API-Key"] = key;
    if (actor) auth["X-Actor"] = actor;
  }
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, body?.error?.message ?? `request failed (${res.status})`);
  }
  return body.data as T;
}

export const api = {
  city: CITY,
  wards: () => call<WardsResponse>(`/wards?city=${CITY}`),
  roofs: (wardId: string) =>
    call<{ basis: string; roofs: RoofItem[] }>(`/wards/${wardId}/buildings?city=${CITY}&top=8`),
  heatType: (wardId: string) =>
    call<{ type: string; confidence: number | null;
           brief: { means?: string; check?: string[]; departments?: string[] } }>(
      `/wards/${wardId}/heat-type?city=${CITY}`),
  recommendations: (wardId: string, lang: string) =>
    call<{ recommendations: Recommendation[]; not_evaluated: { id: string; missing_fields: string[] }[] }>(
      `/wards/${wardId}/recommendations?city=${CITY}&lang=${lang}`),
  forecast: () => call<ForecastFull>(`/forecast/heatdome?city=${CITY}`),
  forecastHistory: () => call<{ forecasts: ForecastFull[] }>(`/forecast/heatdome/history?city=${CITY}`),
  drivers: (w: string) =>
    call<{
      drivers: Driver[];
      unobserved: string[];
      model_card: {
        gbm_spatial_cv_r2: number | null;
        residual_morans_i: number | null;
        features_dropped_vif: string[];
      };
    }>(`/wards/${w}/drivers?city=${CITY}`),
  readiness: (w: string, lang: string) =>
    call<Readiness>(`/wards/${w}/readiness?city=${CITY}&lang=${lang}`),
  soil: (w: string) => call<SoilInfo>(`/wards/${w}/soil?city=${CITY}`),
  fire: () =>
    call<{ events: FireEvent[]; as_of: string | null; note: string }>(`/fire/events?city=${CITY}`),
  protectedAreas: () =>
    call<{ areas: PaPressure[]; geojson: GeoJSON.FeatureCollection | null }>(
      `/protected-areas?city=${CITY}`,
    ),
  facilities: () =>
    fetch(`/api/layers/${CITY}/facilities.geojson`).then((r) => {
      if (!r.ok) throw new ApiError(r.status, "facilities unavailable");
      return r.json() as Promise<GeoJSON.FeatureCollection>;
    }),
  alerts: (ward?: string, staff = false) =>
    call<{ alerts: Alert[]; drafts: Alert[] }>(
      `/alerts?city=${CITY}${ward ? `&ward=${ward}` : ""}`,
      undefined,
      staff,
    ),
  publicAdvisories: () => call<{ advisories: Advisory[] }>(`/advisories/public?city=${CITY}`),
  tts: (advisoryId: string, lang: string) =>
    call<{ audio_url: string | null; fallback?: string; provider: string }>("/tts", {
      method: "POST",
      body: JSON.stringify({ city: CITY, advisory_id: advisoryId, lang }),
    }),
  subscribe: (address: string, channel: string, languages: string[], wardIds?: string[]) =>
    call<{ subscription_id: string; status: string }>("/alerts/subscriptions", {
      method: "POST",
      body: JSON.stringify({ city: CITY, address, channel, languages, ward_ids: wardIds ?? null }),
    }),

  // ---- staff / planner console (needs the planner API key)
  plan: (budget: number) =>
    call<Record<string, unknown> & { csv: string; csv_hash: string }>(
      "/interventions/plan",
      { method: "POST", body: JSON.stringify({ city: CITY, budget_inr: budget }) },
      true,
    ),
  warnings: () =>
    call<{ active: OfficialWarning | null; history: OfficialWarning[] }>(
      `/admin/official-warnings?city=${CITY}`,
      undefined,
      true,
    ),
  addWarning: (w: { level: string; issued_by: string; valid_from: string; valid_until: string; text: string }) =>
    call<OfficialWarning>(
      "/admin/official-warnings",
      { method: "POST", body: JSON.stringify({ city: CITY, ...w }) },
      true,
    ),
  advisories: () => call<{ advisories: Advisory[] }>(`/advisories?city=${CITY}`, undefined, true),
  createAdvisory: (type: string, wardId: string | null, audience?: string) =>
    call<Advisory>(
      "/advisories",
      { method: "POST", body: JSON.stringify({ city: CITY, type, ward_id: wardId, audience }) },
      true,
    ),
  advisoryAction: (id: string, action: "approve" | "publish" | "withdraw") =>
    call<Advisory>(`/advisories/${id}/${action}?city=${CITY}`, { method: "POST" }, true),
  alertAction: (id: string, action: "approve" | "withdraw") =>
    call<Alert>(`/alerts/${id}/${action}?city=${CITY}`, { method: "POST" }, true),
  incidents: () => call<{ incidents: Incident[] }>(`/fire/incidents?city=${CITY}`, undefined, true),
  logIncident: (lat: number, lon: number, notes: string) =>
    call<Incident>(
      "/fire/incidents",
      {
        method: "POST",
        body: JSON.stringify({ city: CITY, lat, lon, time: new Date().toISOString(), notes }),
      },
      true,
    ),
  confirmIncident: (id: string) =>
    call<Incident>(`/fire/incidents/${id}/confirm?city=${CITY}`, { method: "POST" }, true),
  paAlerts: () =>
    call<{ alerts: { code: string; name: string; message: string }[] }>(
      `/protected-areas/alerts?city=${CITY}`,
      undefined,
      true,
    ),
  runAnalysis: () =>
    call<{ execution_id: string; state: string }>(
      "/analysis/heat",
      { method: "POST", body: JSON.stringify({ city: CITY }) },
      true,
    ),
  analysisState: (id: string) =>
    call<{ state: string; steps: string[]; error: string | null }>(
      `/analysis/heat/${id}`,
      undefined,
      true,
    ),
  params: (onlyUnverified: boolean) =>
    call<{ params: { id: string; value: unknown; unit: string | null; status: string; source: string }[] }>(
      `/admin/params?only_unverified=${onlyUnverified}`,
      undefined,
      true,
    ),
  setParam: (id: string, value: unknown, status: string, source: string) =>
    call<{ version: string; changed: string[] }>(
      "/admin/config",
      { method: "PUT", body: JSON.stringify({ overrides: { [id]: { value, status, source } } }) },
      true,
    ),
  tilesUrl: () => `${typeof window === "undefined" ? "" : window.location.origin}/api/tiles/${CITY}/dlst.pmtiles`,
  assess: (body: SolarRequest) =>
    call<SolarResult>("/solar/assess", { method: "POST", body: JSON.stringify(body) }),
  pdf: (assessment: SolarRequest, lang: string) =>
    call<{ url: string }>("/documents/application-pdf", {
      method: "POST", body: JSON.stringify({ assessment, lang }),
    }),
  session: () => call<{ session_id: string }>("/sessions", { method: "POST" }),
  chat: (sessionId: string, message: string, lang: string, wardId?: string) =>
    call<ChatReply>("/agent/chat", {
      method: "POST",
      headers: { "X-Session-ID": sessionId },
      body: JSON.stringify({ message, lang, ward_id: wardId, city: CITY }),
    }),
};
