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
  tabSignals: { en: "Alerts & forecast", hi: "अलर्ट और पूर्वानुमान" },
  tabConsole: { en: "Planner console", hi: "योजनाकार कंसोल" },
  layers: { en: "Map layers", hi: "नक्शे की परतें" },
  colorBy: { en: "Colour wards by", hi: "वार्ड का रंग" },
  byPriority: { en: "Priority rank", hi: "प्राथमिकता क्रम" },
  byDegradation: { en: "Land-degradation indicator", hi: "भूमि क्षरण संकेतक" },
  layerDlst: { en: "ΔLST raster", hi: "ΔLST रास्टर" },
  layerHotspots: { en: "Hotspots", hi: "हॉटस्पॉट" },
  layerFacilities: { en: "Facilities", hi: "सुविधाएँ" },
  layerFire: { en: "Satellite fire detections (last pass)", hi: "उपग्रह आग संकेत (अंतिम गुज़रना)" },
  layerPa: { en: "Protected areas (pressure)", hi: "संरक्षित क्षेत्र (दबाव)" },
  dlstLegend: { en: "ΔLST: cooler → hotter than the rural reference", hi: "ΔLST: ग्रामीण संदर्भ से ठंडा → गर्म" },
  drivers: { en: "What is associated with this ward's heat", hi: "इस वार्ड की गर्मी से क्या जुड़ा है" },
  driversNote: {
    en: "Associated with — not proven causes. Not observed: anthropogenic heat, industrial process heat, roof material.",
    hi: "से जुड़ा — सिद्ध कारण नहीं। अवलोकित नहीं: मानवीय ऊष्मा, औद्योगिक ऊष्मा, छत की सामग्री।",
  },
  warmer: { en: "warmer", hi: "अधिक गर्म" },
  cooler: { en: "cooler", hi: "अधिक ठंडा" },
  unstable: { en: "unstable (models disagree)", hi: "अस्थिर (मॉडल असहमत)" },
  readiness: { en: "Readiness prompts (for officers)", hi: "तैयारी संकेत (अधिकारियों के लिए)" },
  noPrompts: { en: "No readiness prompt is active.", hi: "कोई तैयारी संकेत सक्रिय नहीं है।" },
  hospitals: { en: "hospitals", hi: "अस्पताल" },
  schools: { en: "schools", hi: "स्कूल" },
  coolingPoints: { en: "cooling points", hi: "शीतलन स्थल" },
  nearestHospital: { en: "nearest hospital", hi: "निकटतम अस्पताल" },
  land: { en: "Land indicator (not a diagnosis)", hi: "भूमि संकेतक (निदान नहीं)" },
  signalLabel: { en: "Signal", hi: "संकेत" },
  stability: { en: "stable when a year is dropped", hi: "एक वर्ष हटाने पर स्थिर" },
  officialWarning: { en: "Official warning (entered by staff)", hi: "आधिकारिक चेतावनी (स्टाफ द्वारा दर्ज)" },
  forecastPanel: { en: "Heat-dome forecast signal", hi: "हीट-डोम पूर्वानुमान संकेत" },
  eventProbability: { en: "event probability", hi: "घटना की संभावना" },
  firstDay: { en: "first day", hi: "पहला दिन" },
  duration: { en: "duration (days)", hi: "अवधि (दिन)" },
  tmaxRange: { en: "peak Tmax range (°C)", hi: "अधिकतम तापमान सीमा (°C)" },
  tempOnly: {
    en: "Temperature-only evidence (no pressure-level data): low confidence, capped at 'watch'.",
    hi: "केवल तापमान प्रमाण (दबाव-स्तर डेटा नहीं): कम भरोसा, 'watch' तक सीमित।",
  },
  imdStyle: { en: "Forecast Tmax meets an IMD-style heatwave criterion (not an IMD warning)", hi: "पूर्वानुमानित अधिकतम तापमान IMD-शैली हीटवेव मानदंड पूरा करता है (IMD चेतावनी नहीं)" },
  activeAlerts: { en: "Active alerts", hi: "सक्रिय अलर्ट" },
  noAlerts: { en: "No active public alert.", hi: "कोई सक्रिय सार्वजनिक अलर्ट नहीं।" },
  advisories: { en: "Public advisories", hi: "सार्वजनिक सलाह" },
  listen: { en: "Listen", hi: "सुनें" },
  audioFallback: { en: "Audio unavailable — text only.", hi: "ऑडियो उपलब्ध नहीं — केवल पाठ।" },
  subscribe: { en: "Get alerts by email", hi: "ईमेल से अलर्ट पाएँ" },
  email: { en: "Email address", hi: "ईमेल पता" },
  subscribed: { en: "Subscription saved — confirm via the email you receive.", hi: "सदस्यता सहेजी गई — प्राप्त ईमेल से पुष्टि करें।" },
  fireNote: { en: "Fire detections show the last satellite pass, not real time.", hi: "आग के संकेत उपग्रह का अंतिम गुज़रना दिखाते हैं, वास्तविक समय नहीं।" },
  habitat: { en: "Habitat pressure indicator (unverified — not a measured biodiversity loss)", hi: "आवास दबाव संकेतक (असत्यापित — मापी गई जैव विविधता हानि नहीं)" },
  sketchTitle: { en: "Sketch your roof (optional)", hi: "अपनी छत का नक्शा बनाएँ (वैकल्पिक)" },
  sketchHint: { en: "Click the corners of your roof on the grid (each square = 2 m).", hi: "ग्रिड पर छत के कोनों पर क्लिक करें (हर वर्ग = 2 मी)।" },
  sketchUse: { en: "Use this outline", hi: "यह रूपरेखा उपयोग करें" },
  sketchUndo: { en: "Undo", hi: "पूर्ववत" },
  sketchClear: { en: "Clear", hi: "साफ़ करें" },
  staffLogin: { en: "Staff access", hi: "स्टाफ प्रवेश" },
  apiKey: { en: "Planner API key", hi: "योजनाकार API कुंजी" },
  yourName: { en: "Your name (for the audit trail)", hi: "आपका नाम (ऑडिट के लिए)" },
  saveKey: { en: "Save for this tab", hi: "इस टैब के लिए सहेजें" },
  planBudget: { en: "Budgeted action plan", hi: "बजट आधारित कार्य योजना" },
  budget: { en: "Budget (₹)", hi: "बजट (₹)" },
  makePlan: { en: "Build plan", hi: "योजना बनाएँ" },
  downloadCsv: { en: "Download CSV", hi: "CSV डाउनलोड करें" },
  warningEntry: { en: "Enter an official heatwave warning", hi: "आधिकारिक हीटवेव चेतावनी दर्ज करें" },
  level: { en: "Level", hi: "स्तर" },
  validFrom: { en: "Valid from", hi: "से मान्य" },
  validUntil: { en: "Valid until", hi: "तक मान्य" },
  text: { en: "Text", hi: "पाठ" },
  save: { en: "Save", hi: "सहेजें" },
  composeAdvisory: { en: "Compose advisory", hi: "सलाह बनाएँ" },
  approve: { en: "Approve", hi: "स्वीकृत करें" },
  publish: { en: "Publish", hi: "प्रकाशित करें" },
  withdraw: { en: "Withdraw", hi: "वापस लें" },
  drafts: { en: "Drafts awaiting approval", hi: "स्वीकृति की प्रतीक्षा में मसौदे" },
  incidents: { en: "Fire incidents (staff log)", hi: "आग की घटनाएँ (स्टाफ लॉग)" },
  logIncident: { en: "Log incident", hi: "घटना दर्ज करें" },
  confirm: { en: "Confirm (second person)", hi: "पुष्टि करें (दूसरा व्यक्ति)" },
  rerun: { en: "Re-run heat analysis", hi: "गर्मी विश्लेषण फिर चलाएँ" },
  lat: { en: "Latitude", hi: "अक्षांश" },
  lon: { en: "Longitude", hi: "देशांतर" },
  notes: { en: "Notes", hi: "टिप्पणी" },
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
  brandSub: { en: "FIELD INTELLIGENCE / 01", hi: "फ़ील्ड इंटेलिजेंस / 01" },
  grpWorkspace: { en: "WORKSPACE", hi: "कार्यक्षेत्र" },
  grpTools: { en: "TOOLS", hi: "उपकरण" },
  tabOverview: { en: "Overview", hi: "अवलोकन" },
  crumbRoot: { en: "City", hi: "शहर" },
  lastUpdated: { en: "Last updated", hi: "अंतिम अद्यतन" },
  settings: { en: "Settings", hi: "सेटिंग्स" },
  menu: { en: "Menu", hi: "मेनू" },
  closeMenu: { en: "Close menu", hi: "मेनू बंद करें" },
  notifications: { en: "Alerts", hi: "अलर्ट" },
  cityName: { en: "Demo city", hi: "डेमो शहर" },
  activeWards: { en: "wards assessed", hi: "वार्ड आकलित" },
  localLive: { en: "Local data layer live", hi: "स्थानीय डेटा परत सक्रिय" },
  lastSync: { en: "Last sync", hi: "अंतिम सिंक" },
  userRole: { en: "City planning office", hi: "नगर नियोजन कार्यालय" },
  heroEyebrow: { en: "City heat intelligence", hi: "शहर की गर्मी की जानकारी" },
  heroA: { en: "Cool roofs,", hi: "ठंडी छतें," },
  heroB: { en: "clear priorities.", hi: "स्पष्ट प्राथमिकताएँ।" },
  heroLead: {
    en: "One working view of which wards run hottest, who is exposed, and what to do first — with the source behind every number.",
    hi: "कौन-से वार्ड सबसे गर्म हैं, कौन प्रभावित है और सबसे पहले क्या करें — हर संख्या के स्रोत के साथ एक कार्य-दृश्य।",
  },
  openHeat: { en: "Open heat map", hi: "गर्मी नक्शा खोलें" },
  checkRoof: { en: "Check my roof", hi: "मेरी छत जाँचें" },
  kpiWards: { en: "Wards assessed", hi: "आकलित वार्ड" },
  kpiExposed: { en: "People exposed", hi: "प्रभावित लोग" },
  kpiDlst: { en: "Mean ΔLST", hi: "औसत ΔLST" },
  kpiSignal: { en: "Heat-dome signal", hi: "हीट-डोम संकेत" },
  highestPriority: { en: "First to cool", hi: "सबसे पहले" },
  exposedSub: { en: "Modelled, across all wards", hi: "मॉडल अनुमान, सभी वार्ड" },
  dlstSub: { en: "°C above the rural reference", hi: "°C ग्रामीण संदर्भ से अधिक" },
  signalNone: { en: "No signal", hi: "कोई संकेत नहीं" },
  rankLabel: { en: "Priority ranking", hi: "प्राथमिकता क्रम" },
  rankTitle: { en: "Where to cool first", hi: "पहले कहाँ ठंडा करें" },
  score: { en: "priority", hi: "प्राथमिकता" },
  feedLabel: { en: "Live feed", hi: "लाइव फ़ीड" },
  feedTitle: { en: "Alerts and advisories", hi: "अलर्ट और सलाह" },
  viewAll: { en: "View all", hi: "सभी देखें" },
  hotLabel: { en: "Heat load", hi: "गर्मी का भार" },
  hotTitle: { en: "Hottest wards", hi: "सबसे गर्म वार्ड" },
  readyLabel: { en: "Readiness", hi: "तैयारी" },
  readyTitle: { en: "Facilities in the layer", hi: "परत में सुविधाएँ" },
  facilitiesUnit: { en: "facilities", hi: "सुविधाएँ" },
  workLabel: { en: "Priority wards", hi: "प्राथमिकता वाले वार्ड" },
  workTitle: { en: "First wards to cool", hi: "सबसे पहले ठंडे करने वाले वार्ड" },
  viewHeat: { en: "View heat map", hi: "गर्मी नक्शा देखें" },
  rankN: { en: "Rank", hi: "क्रम" },
  exposedShort: { en: "exposed", hi: "प्रभावित" },
  noData: { en: "Waiting for the API. Start it with: uv run poe api", hi: "API की प्रतीक्षा है। चलाएँ: uv run poe api" },
  pageHeat: { en: "Heat map & ranking", hi: "गर्मी नक्शा और क्रम" },
  pageSolar: { en: "Rooftop solar, checked", hi: "रूफटॉप सोलर, जाँचा हुआ" },
  pageAssistant: { en: "Ask in your language", hi: "अपनी भाषा में पूछें" },
  pageSignals: { en: "Alerts & forecast", hi: "अलर्ट और पूर्वानुमान" },
  pageConsole: { en: "Planner console", hi: "योजनाकार कंसोल" },
  enterApp: { en: "Open the app", hi: "ऐप खोलें" },
  backHome: { en: "Home page", hi: "मुख्य पृष्ठ" },
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
