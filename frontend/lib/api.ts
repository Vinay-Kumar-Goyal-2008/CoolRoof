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

export class ApiError extends Error {
  constructor(public code: number, message: string) {
    super(message);
  }
}

const CITY = process.env.NEXT_PUBLIC_CITY ?? "mini_city";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
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
  forecast: () => call<Forecast>(`/forecast/heatdome?city=${CITY}`),
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
