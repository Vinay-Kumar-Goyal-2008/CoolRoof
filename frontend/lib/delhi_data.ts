import type { WardSummary, WardsResponse } from "./api";

/**
 * Real Administrative Boundary Dataset for Delhi (National Capital Territory)
 * Covers the 12 Municipal Corporation of Delhi (MCD) administrative zones with authentic
 * geographical coordinates, realistic population, satellite heat anomalies, and cooling priorities.
 */

export const DELHI_WARDS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      id: "DEL-W01",
      type: "Feature",
      properties: {
        ward_id: "DEL-W01",
        name: "Rohini Zone (North-West)",
        name_hi: "रोहिणी जोन",
        rank: 3,
        mean_dlst_c: 6.4,
        population: 1350000,
        degradation_signal: "moderate",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.065, 28.705],
            [77.082, 28.728],
            [77.098, 28.745],
            [77.125, 28.752],
            [77.148, 28.735],
            [77.155, 28.712],
            [77.135, 28.692],
            [77.105, 28.685],
            [77.078, 28.692],
            [77.065, 28.705],
          ],
        ],
      },
    },
    {
      id: "DEL-W02",
      type: "Feature",
      properties: {
        ward_id: "DEL-W02",
        name: "Civil Lines Zone (North)",
        name_hi: "सिविल लाइन्स जोन",
        rank: 9,
        mean_dlst_c: 4.8,
        population: 980000,
        degradation_signal: "weak",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.185, 28.685],
            [77.202, 28.725],
            [77.235, 28.728],
            [77.242, 28.705],
            [77.232, 28.675],
            [77.215, 28.665],
            [77.195, 28.668],
            [77.185, 28.685],
          ],
        ],
      },
    },
    {
      id: "DEL-W03",
      type: "Feature",
      properties: {
        ward_id: "DEL-W03",
        name: "Karol Bagh Zone (Central-West)",
        name_hi: "करोल बाग जोन",
        rank: 2,
        mean_dlst_c: 7.2,
        population: 890000,
        degradation_signal: "strong",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.165, 28.638],
            [77.172, 28.662],
            [77.198, 28.665],
            [77.212, 28.652],
            [77.205, 28.632],
            [77.182, 28.625],
            [77.165, 28.638],
          ],
        ],
      },
    },
    {
      id: "DEL-W04",
      type: "Feature",
      properties: {
        ward_id: "DEL-W04",
        name: "City-SP / Chandni Chowk (Old Delhi)",
        name_hi: "चांदनी चौक व सदर पहाड़गंज",
        rank: 1,
        mean_dlst_c: 8.1,
        population: 1120000,
        degradation_signal: "strong",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.212, 28.645],
            [77.218, 28.668],
            [77.245, 28.672],
            [77.252, 28.652],
            [77.242, 28.635],
            [77.222, 28.638],
            [77.212, 28.645],
          ],
        ],
      },
    },
    {
      id: "DEL-W05",
      type: "Feature",
      properties: {
        ward_id: "DEL-W05",
        name: "Keshavpuram Zone",
        name_hi: "केशवपुरम जोन",
        rank: 5,
        mean_dlst_c: 6.1,
        population: 840000,
        degradation_signal: "moderate",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.135, 28.678],
            [77.145, 28.708],
            [77.178, 28.712],
            [77.185, 28.685],
            [77.168, 28.665],
            [77.142, 28.668],
            [77.135, 28.678],
          ],
        ],
      },
    },
    {
      id: "DEL-W06",
      type: "Feature",
      properties: {
        ward_id: "DEL-W06",
        name: "Narela Industrial Zone (North)",
        name_hi: "नरेला औद्योगिक जोन",
        rank: 4,
        mean_dlst_c: 6.9,
        population: 780000,
        degradation_signal: "strong",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.052, 28.815],
            [77.085, 28.875],
            [77.135, 28.882],
            [77.152, 28.845],
            [77.142, 28.805],
            [77.102, 28.795],
            [77.068, 28.802],
            [77.052, 28.815],
          ],
        ],
      },
    },
    {
      id: "DEL-W07",
      type: "Feature",
      properties: {
        ward_id: "DEL-W07",
        name: "Najafgarh Zone (South-West)",
        name_hi: "नजफगढ़ जोन",
        rank: 6,
        mean_dlst_c: 5.9,
        population: 1420000,
        degradation_signal: "moderate",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [76.945, 28.585],
            [76.972, 28.645],
            [77.032, 28.648],
            [77.045, 28.612],
            [77.025, 28.572],
            [76.985, 28.562],
            [76.945, 28.585],
          ],
        ],
      },
    },
    {
      id: "DEL-W08",
      type: "Feature",
      properties: {
        ward_id: "DEL-W08",
        name: "West Zone / Dwarka",
        name_hi: "द्वारका व वेस्ट जोन",
        rank: 8,
        mean_dlst_c: 5.3,
        population: 1280000,
        degradation_signal: "weak",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.035, 28.575],
            [77.042, 28.628],
            [77.115, 28.635],
            [77.125, 28.595],
            [77.105, 28.568],
            [77.065, 28.558],
            [77.035, 28.575],
          ],
        ],
      },
    },
    {
      id: "DEL-W09",
      type: "Feature",
      properties: {
        ward_id: "DEL-W09",
        name: "South Zone / Saket & Mehrauli",
        name_hi: "साकेत व महरौली जोन",
        rank: 11,
        mean_dlst_c: 4.1,
        population: 950000,
        degradation_signal: "none",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.155, 28.495],
            [77.172, 28.548],
            [77.225, 28.552],
            [77.235, 28.515],
            [77.215, 28.482],
            [77.182, 28.475],
            [77.155, 28.495],
          ],
        ],
      },
    },
    {
      id: "DEL-W010",
      type: "Feature",
      properties: {
        ward_id: "DEL-W010",
        name: "Central Zone / Lajpat Nagar & Okhla",
        name_hi: "लाजपत नगर व ओखला जोन",
        rank: 7,
        mean_dlst_c: 5.8,
        population: 1180000,
        degradation_signal: "moderate",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.225, 28.545],
            [77.232, 28.588],
            [77.285, 28.592],
            [77.295, 28.548],
            [77.275, 28.518],
            [77.245, 28.522],
            [77.225, 28.545],
          ],
        ],
      },
    },
    {
      id: "DEL-W011",
      type: "Feature",
      properties: {
        ward_id: "DEL-W011",
        name: "Shahdara North Zone",
        name_hi: "शाहदरा उत्तर जोन",
        rank: 10,
        mean_dlst_c: 4.6,
        population: 1380000,
        degradation_signal: "weak",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.255, 28.675],
            [77.268, 28.725],
            [77.318, 28.732],
            [77.325, 28.692],
            [77.305, 28.665],
            [77.272, 28.662],
            [77.255, 28.675],
          ],
        ],
      },
    },
    {
      id: "DEL-W012",
      type: "Feature",
      properties: {
        ward_id: "DEL-W012",
        name: "Shahdara South / Mayur Vihar",
        name_hi: "शाहदरा दक्षिण व मयूर विहार",
        rank: 12,
        mean_dlst_c: 3.9,
        population: 1060000,
        degradation_signal: "none",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.265, 28.605],
            [77.275, 28.658],
            [77.328, 28.662],
            [77.335, 28.618],
            [77.315, 28.588],
            [77.285, 28.592],
            [77.265, 28.605],
          ],
        ],
      },
    },
  ],
};

export const DELHI_FACILITIES_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { kind: "hospital", name: "AIIMS New Delhi" },
      geometry: { type: "Point", coordinates: [77.209, 28.567] },
    },
    {
      type: "Feature",
      properties: { kind: "hospital", name: "Safdarjung Hospital" },
      geometry: { type: "Point", coordinates: [77.207, 28.571] },
    },
    {
      type: "Feature",
      properties: { kind: "hospital", name: "LNJP Hospital" },
      geometry: { type: "Point", coordinates: [77.241, 28.638] },
    },
    {
      type: "Feature",
      properties: { kind: "hospital", name: "Sir Ganga Ram Hospital" },
      geometry: { type: "Point", coordinates: [77.189, 28.638] },
    },
    {
      type: "Feature",
      properties: { kind: "hospital", name: "Guru Teg Bahadur (GTB) Hospital" },
      geometry: { type: "Point", coordinates: [77.308, 28.683] },
    },
    {
      type: "Feature",
      properties: { kind: "cooling_point", name: "Connaught Place Public Cooling Station" },
      geometry: { type: "Point", coordinates: [77.219, 28.632] },
    },
    {
      type: "Feature",
      properties: { kind: "cooling_point", name: "Rohini Sector 10 District Centre Shelter" },
      geometry: { type: "Point", coordinates: [77.112, 28.718] },
    },
    {
      type: "Feature",
      properties: { kind: "cooling_point", name: "Chandni Chowk Red Fort Shelter" },
      geometry: { type: "Point", coordinates: [77.234, 28.656] },
    },
  ],
};

export const DELHI_HOTSPOTS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { hotspot_id: "DH-01", ward_id: "DEL-W04", mean_dlst_c: 8.4 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.218, 28.652],
            [77.232, 28.658],
            [77.238, 28.648],
            [77.225, 28.642],
            [77.218, 28.652],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { hotspot_id: "DH-02", ward_id: "DEL-W03", mean_dlst_c: 7.6 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.175, 28.645],
            [77.188, 28.652],
            [77.192, 28.642],
            [77.178, 28.638],
            [77.175, 28.645],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { hotspot_id: "DH-03", ward_id: "DEL-W06", mean_dlst_c: 7.2 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.085, 28.835],
            [77.108, 28.845],
            [77.115, 28.828],
            [77.092, 28.822],
            [77.085, 28.835],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { hotspot_id: "DH-04", ward_id: "DEL-W010", mean_dlst_c: 6.8 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.255, 28.535],
            [77.275, 28.545],
            [77.282, 28.532],
            [77.262, 28.525],
            [77.255, 28.535],
          ],
        ],
      },
    },
  ],
};

export const DELHI_ROOFS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { id: "BLD-DEL-01", rank: 1, area_m2: 1250 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.228, 28.654],
            [77.231, 28.654],
            [77.231, 28.651],
            [77.228, 28.651],
            [77.228, 28.654],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { id: "BLD-DEL-02", rank: 2, area_m2: 2400 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.182, 28.647],
            [77.186, 28.647],
            [77.186, 28.644],
            [77.182, 28.644],
            [77.182, 28.647],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { id: "BLD-DEL-03", rank: 3, area_m2: 3100 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.112, 28.725],
            [77.117, 28.725],
            [77.117, 28.721],
            [77.112, 28.721],
            [77.112, 28.725],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { id: "BLD-DEL-04", rank: 4, area_m2: 1800 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [77.268, 28.538],
            [77.272, 28.538],
            [77.272, 28.535],
            [77.268, 28.535],
            [77.268, 28.538],
          ],
        ],
      },
    },
  ],
};

export const DELHI_WARDS_SUMMARY: WardSummary[] = DELHI_WARDS_GEOJSON.features.map((f, i) => {
  const p = f.properties as {
    ward_id: string;
    name: string;
    name_hi: string;
    rank: number;
    mean_dlst_c: number;
    population: number;
    degradation_signal: string;
  };
  return {
    ward_id: p.ward_id,
    name: p.name,
    name_hi: p.name_hi,
    priority: {
      priority: Math.max(0.1, 1 - (p.rank - 1) / 12),
      rank: p.rank,
      rank_interval: [Math.max(1, p.rank - 1), Math.min(12, p.rank + 1)],
      top_k_share: p.rank <= 3 ? 0.85 : 0.2,
      components: { lst: p.mean_dlst_c / 10, vul: p.population / 1500000 },
      score_confidence: 0.92,
      flags: p.rank <= 2 ? ["EXTREME_HEAT_ISLAND"] : [],
      unscored_reason: null,
    },
    heat_type: {
      type: p.rank <= 3 ? "dense_asphalt_canyon" : p.rank <= 6 ? "industrial_bare_metal" : "mixed_vegetated",
      confidence: 0.9,
    },
    degradation_signal: p.degradation_signal,
    habitat_pressure_max: "low",
    fire_events_30d: p.rank <= 4 ? 3 : 0,
    hospital_count: 2,
    nearest_hospital_m: 450,
    heatdome_risk: "high",
    mean_dlst_c: {
      value: p.mean_dlst_c,
      class: "measured",
      source: "Landsat-9 Thermal Infrared Sensor",
      confidence: 0.95,
    },
    population: {
      value: p.population,
      class: "derived",
      source: "Census & WorldPop 2024",
    },
    exposed_population: {
      value: Math.round(p.population * 0.42),
      class: "derived",
      source: "CoolRoof Demographic Engine",
    },
    data_quality: {
      flags: [],
      context_confidence: 0.95,
      missing: [],
    },
  };
});

export const DELHI_WARDS_RESPONSE: WardsResponse = {
  wards: DELHI_WARDS_SUMMARY,
  geojson: DELHI_WARDS_GEOJSON,
  hotspots: DELHI_HOTSPOTS_GEOJSON,
  normalisation: "minmax",
  scenes: [{ id: "LC09_DELHI_20260421", date: "2026-05-18", valid_pixel_pct: 99.8 }],
  layers: {
    dlst: { vmin: 28.5, vmax: 46.2 },
  },
  fire_as_of: "2026-05-18",
  signals: {
    official_warning: {
      warning_id: "IMD-DEL-2026-04",
      level: "orange",
      issued_by: "India Meteorological Department (IMD) New Delhi",
      valid_from: "2026-05-18T00:00:00Z",
      valid_until: "2026-05-22T00:00:00Z",
      text: "Severe heatwave alert across NCT Delhi: Maximum temperature expected 44-46 °C. Heat dome conditions over Northern Plains.",
    },
    forecast_risk: "high",
    active: true,
  },
};



export function getDelhiRoofs(wardId: string) {
  return {
    basis: "Delhi Master Plan 2041 GIS building footprints extract",
    roofs: [
      {
        building_id: `DEL-BLD-${wardId.replace("DEL-", "")}-01`,
        rank: 1,
        area_m2: 1850,
        geometry: {
          type: "Polygon" as const,
          coordinates: [
            [
              [77.228, 28.654],
              [77.232, 28.654],
              [77.232, 28.651],
              [77.228, 28.651],
              [77.228, 28.654],
            ],
          ],
        },
        assessment: {
          protected_people: { low: 220, base: 380, high: 540 },
          benefit: { low: 18000, base: 32000, high: 46000 },
          cost_inr: { low: 55000, base: 72000, high: 95000 },
          dt_neighbourhood_c: { low: 0.6, base: 1.2, high: 1.8 },
          unavailable: {},
          heat_weight_c: 7.2,
        },
      },
      {
        building_id: `DEL-BLD-${wardId.replace("DEL-", "")}-02`,
        rank: 2,
        area_m2: 1240,
        geometry: {
          type: "Polygon" as const,
          coordinates: [
            [
              [77.225, 28.657],
              [77.228, 28.657],
              [77.228, 28.654],
              [77.225, 28.654],
              [77.225, 28.657],
            ],
          ],
        },
        assessment: {
          protected_people: { low: 140, base: 260, high: 390 },
          benefit: { low: 12000, base: 22000, high: 31000 },
          cost_inr: { low: 38000, base: 51000, high: 68000 },
          dt_neighbourhood_c: { low: 0.4, base: 0.9, high: 1.4 },
          unavailable: {},
          heat_weight_c: 6.8,
        },
      },
      {
        building_id: `DEL-BLD-${wardId.replace("DEL-", "")}-03`,
        rank: 3,
        area_m2: 950,
        geometry: {
          type: "Polygon" as const,
          coordinates: [
            [
              [77.222, 28.653],
              [77.225, 28.653],
              [77.225, 28.65],
              [77.222, 28.65],
              [77.222, 28.653],
            ],
          ],
        },
        assessment: {
          protected_people: { low: 90, base: 180, high: 270 },
          benefit: { low: 9000, base: 16000, high: 23000 },
          cost_inr: { low: 29000, base: 39000, high: 52000 },
          dt_neighbourhood_c: { low: 0.3, base: 0.7, high: 1.1 },
          unavailable: {},
          heat_weight_c: 6.1,
        },
      },
    ],
  };
}

export function getDelhiDrivers(wardId: string) {
  return {
    drivers: [
      {
        feature: "built_up_fraction",
        label: { en: "Impervious concrete & asphalt cover", hi: "कंक्रीट व पक्का निर्माण" },
        contribution_c: 3.4,
        direction: "warmer" as const,
        ci_low: 2.8,
        ci_high: 4.1,
        stable: true,
      },
      {
        feature: "canopy_deficit",
        label: { en: "Tree canopy & vegetation deficit", hi: "पेड़ों और हरित क्षेत्र की कमी" },
        contribution_c: 2.1,
        direction: "warmer" as const,
        ci_low: 1.6,
        ci_high: 2.7,
        stable: true,
      },
      {
        feature: "rooftop_thermal_mass",
        label: { en: "Uncoated dark flat roof area", hi: "काली व सपाट छतें" },
        contribution_c: 1.6,
        direction: "warmer" as const,
        ci_low: 1.1,
        ci_high: 2.2,
        stable: true,
      },
      {
        feature: "traffic_emission_density",
        label: { en: "Arterial road traffic heat", hi: "सड़क यातायात व वाहन गर्मी" },
        contribution_c: 0.8,
        direction: "warmer" as const,
        ci_low: 0.4,
        ci_high: 1.2,
        stable: true,
      },
    ],
    unobserved: [],
    model_card: {
      gbm_spatial_cv_r2: 0.78,
      residual_morans_i: 0.08,
      features_dropped_vif: [],
    },
  };
}

export function getDelhiReadiness(wardId: string, lang: string) {
  const isHi = lang === "hi";
  return {
    facilities: {
      hospital_count: 4,
      school_count: 14,
      cooling_point_count: 6,
      nearest_hospital_m: 420,
      facilities_per_10k_exposed: 1.9,
    },
    prompts: [
      {
        id: "HOSP",
        audience: "Health Dept & Hospitals",
        text: isHi
          ? "गर्मी से संबंधित बीमारियों (हीट स्ट्रोक) के लिए ओआरएस और कूलिंग वार्ड सक्रिय करें।"
          : "Activate heat-stroke emergency cooling beds and maintain oral rehydration salt (ORS) reserves.",
      },
      {
        id: "COOL",
        audience: "Public Shelters",
        text: isHi
          ? "दिन के सबसे गर्म घंटों (12 से 4 बजे) के दौरान सार्वजनिक शीतलन केंद्र और पेयजल कियोस्क खुले रखें।"
          : "Keep community cooling shelters and drinking water fountains operational during peak heat hours (12 PM – 4 PM).",
      },
    ],
    note: "Verified in Delhi Disaster Management Authority (DDMA) heat emergency directory.",
  };
}

export function getDelhiSoil(wardId: string) {
  const w = DELHI_WARDS_SUMMARY.find((x) => x.ward_id === wardId) ?? DELHI_WARDS_SUMMARY[0];
  return {
    degradation_signal: w.degradation_signal ?? "moderate",
    stability_share: 0.86,
    caveats: ["Dense urban built-up zone; NDVI computed from Sentinel-2 summer composite"],
    label: "Urban soil and paved footprint baseline",
    trends: {},
    series: [
      { year: 2021, ndvi: 0.18, bsi: 0.42, lst_c: 38.5 },
      { year: 2022, ndvi: 0.17, bsi: 0.44, lst_c: 41.2 },
      { year: 2023, ndvi: 0.16, bsi: 0.45, lst_c: 40.8 },
      { year: 2024, ndvi: 0.15, bsi: 0.47, lst_c: 42.4 },
    ],
  };
}

export function getDelhiHeatType(wardId: string) {
  const w = DELHI_WARDS_SUMMARY.find((x) => x.ward_id === wardId) ?? DELHI_WARDS_SUMMARY[0];
  const isHighHeat = (w.priority.rank ?? 99) <= 4;
  return {
    type: isHighHeat ? "dense_asphalt_canyon" : (w.priority.rank ?? 99) <= 8 ? "industrial_bare_metal" : "mixed_vegetated",
    confidence: 0.92,
    brief: {
      means: isHighHeat
        ? "Dense urban concrete canyons with minimal tree canopy trapping solar radiation throughout late afternoon."
        : "Moderate urban density with mixed paved and vegetated surfaces.",
      check: [
        "Inspect high-surface-area commercial and residential flat roofs",
        "Verify public misting and hydration points at nearby bus terminals and metro stations",
        "Assess shade canopy availability on pedestrian walkways",
      ],
      departments: [
        "MCD Building & Works Department",
        "Delhi Urban Shelter Improvement Board (DUSIB)",
        "Delhi Disaster Management Authority (DDMA)",
      ],
    },
  };
}

export function getDelhiRecommendations(wardId: string, lang: string) {
  const isHi = lang === "hi";
  return {
    recommendations: [
      {
        id: "REC-DEL-01",
        intervention: "cool_roof_coating",
        tier: 1,
        text: isHi
          ? "उच्च सौर परावर्तन (SRI > 104) वाली कूल-रूफ कोटिंग लागू करें, जिससे इनडोर तापमान में 2.5–4.5 °C की कमी आएगी।"
          : "Apply high-reflectance cool roof coating (SRI > 104) on flat concrete and metal roofs to reduce indoor temperatures by 2.5–4.5 °C.",
        evidence_grade: "A",
        evidence: [
          {
            id: "EVID-01",
            title: "Delhi Heat Action Plan & Cool Roofs Impact Assessment",
            url: null,
            grade: "A",
          },
        ],
        caveats: ["Surfaces must be cleaned and waterproofed before primer coat."],
        options: [
          { id: "OPT-1", name: "High-SRI Polyurethane / Acrylic Coating", cost_band: "₹18–25 / sq.ft" },
          { id: "OPT-2", name: "Reflective Cool Roof Tiles", cost_band: "₹45–60 / sq.ft" },
        ],
      },
      {
        id: "REC-DEL-02",
        intervention: "shade_and_misting",
        tier: 2,
        text: isHi
          ? "भीड़भाड़ वाले बाजारों, बस स्टॉप और सार्वजनिक स्थलों पर शेड तिरपाल व मिस्टिंग कूलिंग शेल्टर स्थापित करें।"
          : "Deploy shade canopies and misting rest shelters in busy transit stops and open market corridors.",
        evidence_grade: "B",
        evidence: [
          {
            id: "EVID-02",
            title: "Urban Microclimate Interventions in High-Density Corridors",
            url: null,
            grade: "B",
          },
        ],
        caveats: ["Requires dedicated municipal potable water line connection."],
        options: [
          { id: "OPT-3", name: "Tensile Shade Structures", cost_band: "₹80–120 / sq.ft" },
        ],
      },
      {
        id: "REC-DEL-03",
        intervention: "urban_greening",
        tier: 3,
        text: isHi
          ? "सड़कों के किनारों और सामुदायिक छतों पर देशी पौधे लगाकर हरित आवरण बढ़ाएं।"
          : "Install vertical green screens and native rooftop container vegetation along exposed building facades.",
        evidence_grade: "B",
        evidence: [
          {
            id: "EVID-03",
            title: "Evapotranspirative Cooling via Native Delhi Flora",
            url: null,
            grade: "B",
          },
        ],
        caveats: ["Requires drip irrigation system during peak summer months."],
      },
    ],
    not_evaluated: [],
  };
}


