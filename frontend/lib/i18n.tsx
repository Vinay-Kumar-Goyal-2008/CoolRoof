"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type Lang = "en" | "hi";

const DICT = {
  appTitle: { en: "CoolRoof", hi: "कूलरूफ" },
  tagline: {
    en: "Which roofs should a city cool first — and can your home go solar?",
    hi: "शहर को पहले कौन-सी छतें ठंडी करनी चाहिए — और क्या आपका घर सोलर हो सकता है?",
  },
  tabHeat: { en: "Heat map", hi: "गर्मी नक्शा" },
  tabSolar: { en: "Rooftop solar", hi: "रूफटॉप सोलर" },
  tabAssistant: { en: "Assistant", hi: "सहायक" },
  lstNote: {
    en: "Heat is the surface temperature at a late-morning satellite pass (about 100 m pixels) — not air temperature, and individual roofs cannot be resolved.",
    hi: "गर्मी सुबह के उपग्रह गुज़रने के समय की सतह का तापमान है (लगभग 100 मी पिक्सेल) — हवा का तापमान नहीं, और अलग-अलग छतें नहीं पहचानी जा सकतीं।",
  },
  mapLegend: { en: "Priority rank (1 = first to cool)", hi: "प्राथमिकता क्रम (1 = सबसे पहले)" },
  ranking: { en: "Ward ranking", hi: "वार्ड क्रम" },
  rank: { en: "Rank", hi: "क्रम" },
  rankRange: { en: "plausible rank range", hi: "संभावित क्रम सीमा" },
  selectWard: { en: "Select a ward on the map or list.", hi: "नक्शे या सूची से वार्ड चुनें।" },
  heatAbove: { en: "above rural reference", hi: "ग्रामीण संदर्भ से अधिक" },
  people: { en: "people", hi: "लोग" },
  exposed: { en: "exposed to heat", hi: "गर्मी के संपर्क में" },
  heatType: { en: "Heat type", hi: "गर्मी का प्रकार" },
  whatItMeans: { en: "What it means", hi: "इसका मतलब" },
  toCheck: { en: "Check on the ground", hi: "ज़मीन पर जाँचें" },
  departments: { en: "Departments", hi: "विभाग" },
  recommendations: { en: "Recommendations (rule-based, with evidence)", hi: "सिफ़ारिशें (नियम-आधारित, साक्ष्य सहित)" },
  evidence: { en: "Evidence", hi: "साक्ष्य" },
  notEvaluated: { en: "Not evaluated (data missing)", hi: "मूल्यांकन नहीं हुआ (डेटा अनुपलब्ध)" },
  topRoofs: { en: "Top roofs to cool", hi: "ठंडी करने वाली शीर्ष छतें" },
  roofsWithheld: { en: "Roof ranking withheld", hi: "छत क्रम रोका गया" },
  protected: { en: "people protected", hi: "सुरक्षित लोग" },
  costUnavailable: {
    en: "Cost not available: coating cost per m² is not verified yet.",
    hi: "लागत उपलब्ध नहीं: प्रति वर्ग मीटर कोटिंग लागत अभी सत्यापित नहीं है।",
  },
  heatDome: { en: "Heat-dome forecast signal", hi: "हीट-डोम पूर्वानुमान संकेत" },
  heatDomeNote: { en: "Forecast signal, not an official warning.", hi: "पूर्वानुमान संकेत, आधिकारिक चेतावनी नहीं।" },
  solarTitle: { en: "Check rooftop solar for your home", hi: "अपने घर के लिए रूफटॉप सोलर जाँचें" },
  roofArea: { en: "Roof area (m²)", hi: "छत का क्षेत्रफल (वर्ग मी)" },
  monthlyUnits: { en: "Monthly electricity (units)", hi: "मासिक बिजली (यूनिट)" },
  grossCost: { en: "Installer quote (₹, optional)", hi: "इंस्टॉलर का कोटेशन (₹, वैकल्पिक)" },
  check: { en: "Check", hi: "जाँचें" },
  systemSize: { en: "Recommended system", hi: "अनुशंसित सिस्टम" },
  generation: { en: "Year-1 generation (range)", hi: "पहले वर्ष का उत्पादन (सीमा)" },
  subsidy: { en: "PM Surya Ghar subsidy", hi: "पीएम सूर्य घर सब्सिडी" },
  payback: { en: "Payback", hi: "लागत वापसी" },
  years: { en: "years", hi: "वर्ष" },
  paybackNeed: {
    en: "Add your monthly units and an installer quote to see payback.",
    hi: "लागत वापसी देखने के लिए मासिक यूनिट और इंस्टॉलर कोटेशन जोड़ें।",
  },
  downloadPdf: { en: "Download PDF summary", hi: "PDF सारांश डाउनलोड करें" },
  assistantHint: {
    en: "Ask in English or Hindi, e.g. “How much subsidy for my 70 m² roof, 400 units?”",
    hi: "हिंदी या English में पूछें, जैसे “70 वर्ग मी छत, 400 यूनिट पर कितनी सब्सिडी?”",
  },
  send: { en: "Send", hi: "भेजें" },
  typeMessage: { en: "Type your question", hi: "अपना प्रश्न लिखें" },
  loading: { en: "Loading…", hi: "लोड हो रहा है…" },
  error: { en: "Something went wrong", hi: "कुछ गड़बड़ हो गई" },
  unavailable: { en: "unavailable", hi: "अनुपलब्ध" },
  syntheticNote: {
    en: "Demo uses a synthetic city and a synthetic tariff.",
    hi: "डेमो में कृत्रिम शहर और कृत्रिम टैरिफ़ का उपयोग हुआ है।",
  },
  disclaimer: {
    en: "Assistance summary — not the official application. Apply at pmsuryaghar.gov.in.",
    hi: "सहायता सारांश — आधिकारिक आवेदन नहीं। pmsuryaghar.gov.in पर आवेदन करें।",
  },
} as const;

export type Key = keyof typeof DICT;

interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key) => string;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("coolroof-lang");
      if (saved === "en" || saved === "hi") setLangState(saved);
    } catch { /* storage unavailable: keep default */ }
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    document.documentElement.lang = l;
    try { window.localStorage.setItem("coolroof-lang", l); } catch { /* ignore */ }
  }, []);

  const value = useMemo<I18n>(
    () => ({ lang, setLang, t: (key) => DICT[key][lang] }),
    [lang, setLang],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}

/** Indian digit grouping, e.g. 150000 → 1,50,000. */
export function fmt(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
