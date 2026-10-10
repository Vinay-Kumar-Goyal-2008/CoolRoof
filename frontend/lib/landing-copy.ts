import type { Lang } from "./i18n";

export interface LandingCopy {
  navFeatures: string; navTrust: string; navHow: string; open: string;
  eyebrow: string; h1a: string; h1b: string; lead: string; ctaPrimary: string; ctaSecondary: string;
  vizTitle: string; vizFirst: string; vizLast: string; vizNote: string; vizOffline: string;
  stripWards: string; stripExposed: string; stripDlst: string; stripFirst: string;
  featuresH: string; featuresLead: string;
  f1h: string; f1p: string; f1l: string[];
  f2h: string; f2p: string; f2l: string[]; f2Cap: string;
  f3h: string; f3p: string; f3l: string[];
  trustH: string; trustLead: string;
  rules: [string, string][];
  ctaH: string; ctaP: string;
  footA: string; footB: string;
  solarRows: [string, string][];
  alertRows: [string, string][];
}

export const COPY: Record<Lang, LandingCopy> = {
  en: {
    navFeatures: "What it does", navTrust: "Why trust it", navHow: "For officers", open: "Open the app",
    eyebrow: "Heat intelligence + rooftop solar",
    h1a: "Cool the right roofs,", h1b: "first.",
    lead: "CoolRoof ranks a city’s wards by heat load and exposure, shows what is associated with each ward’s heat, and checks rooftop solar for any home — with the source and confidence behind every number.",
    ctaPrimary: "Open the app", ctaSecondary: "See how it works",
    vizTitle: "Ward priority, live from the API", vizFirst: "cool first", vizLast: "later",
    vizNote: "Surface temperature at a late-morning satellite pass, not air temperature. Demo city.",
    vizOffline: "Start the API to see the live ward map here.",
    stripWards: "Wards assessed", stripExposed: "People exposed", stripDlst: "Mean ΔLST above rural", stripFirst: "First to cool",
    featuresH: "Three jobs, one working view.",
    featuresLead: "Built for city heat-action teams and for households deciding about solar.",
    f1h: "Know which wards to cool first",
    f1p: "A transparent priority score from satellite surface heat, exposed population and vulnerability, with a plausible rank range instead of a falsely exact number.",
    f1l: ["Map layers: ΔLST raster, hotspots, facilities, satellite fire detections, protected areas", "Drivers shown as ‘associated with’, never as proven causes", "Top roofs per ward, with cost withheld until verified"],
    f2h: "Check rooftop solar in a minute",
    f2p: "Enter roof area and monthly units. Get a recommended system size, the PM Surya Ghar subsidy with its policy version and source, and a payback range.",
    f2l: ["Sketch your roof outline on a grid to measure its area", "Subsidy is policy fact; generation and payback are labelled estimates", "A PDF summary — not the official application"],
    f2Cap: "Example: 70 m² roof, 400 units a month, demo tariff.",
    f3h: "Alerts you can trust, in English and हिंदी",
    f3p: "Planners enter official warnings and approve public advisories with a two-person check. The public sees what is active, can listen to it, and can ask the assistant.",
    f3l: ["Heat-dome signal is a forecast signal, never an official warning", "Advisories need approval before they publish", "The assistant only states numbers its tools returned"],
    trustH: "Every number says where it came from.",
    trustLead: "Heat and solar decisions get argued over. CoolRoof keeps the evidence attached.",
    rules: [
      ["Provenance on every value", "Measured, derived, estimated, policy, user-supplied or unavailable — with source, date and resolution on hover."],
      ["Indicators, not diagnoses", "Land and habitat signals are labelled as indicators. Unavailable data is explained, never left blank."],
      ["Honest limits", "Surface temperature at a late-morning satellite pass is not air temperature, and single roofs cannot be resolved at this pixel size."],
    ],
    ctaH: "See your city’s hottest wards.",
    ctaP: "The app runs locally against the demo city and a synthetic tariff.",
    footA: "Assistance summary — not the official application. Apply at pmsuryaghar.gov.in.",
    footB: "Demo uses a synthetic city and a synthetic tariff.",
    solarRows: [["System", "3 kW"], ["Subsidy", "₹78,000"], ["Payback", "estimate range"]],
    alertRows: [["Official warning", "entered by staff"], ["Heat-dome signal", "forecast, not a warning"], ["Public advisory", "approved, with audio"]],
  },
  hi: {
    navFeatures: "क्या करता है", navTrust: "भरोसा क्यों", navHow: "अधिकारियों के लिए", open: "ऐप खोलें",
    eyebrow: "गर्मी की जानकारी + रूफटॉप सोलर",
    h1a: "सही छतें ठंडी करें,", h1b: "सबसे पहले।",
    lead: "कूलरूफ शहर के वार्डों को गर्मी के भार और प्रभावित आबादी के आधार पर क्रम देता है, बताता है कि हर वार्ड की गर्मी से क्या जुड़ा है, और किसी भी घर के लिए रूफटॉप सोलर जाँचता है — हर संख्या के स्रोत और भरोसे के साथ।",
    ctaPrimary: "ऐप खोलें", ctaSecondary: "यह कैसे काम करता है",
    vizTitle: "वार्ड प्राथमिकता, API से लाइव", vizFirst: "पहले ठंडा करें", vizLast: "बाद में",
    vizNote: "सुबह के उपग्रह गुज़रने के समय की सतह का तापमान, हवा का तापमान नहीं। डेमो शहर।",
    vizOffline: "लाइव वार्ड नक्शा देखने के लिए API चालू करें।",
    stripWards: "आकलित वार्ड", stripExposed: "प्रभावित लोग", stripDlst: "ग्रामीण से औसत ΔLST", stripFirst: "सबसे पहले",
    featuresH: "तीन काम, एक कार्य-दृश्य।",
    featuresLead: "शहर की गर्मी-कार्य टीमों और सोलर पर निर्णय लेने वाले परिवारों के लिए।",
    f1h: "जानें कि कौन-से वार्ड पहले ठंडे करें",
    f1p: "उपग्रह सतह-गर्मी, प्रभावित आबादी और संवेदनशीलता से बना पारदर्शी प्राथमिकता स्कोर — झूठी सटीक संख्या के बजाय संभावित क्रम सीमा के साथ।",
    f1l: ["नक्शे की परतें: ΔLST रास्टर, हॉटस्पॉट, सुविधाएँ, उपग्रह आग संकेत, संरक्षित क्षेत्र", "कारण ‘से जुड़े’ दिखते हैं, सिद्ध कारण नहीं", "हर वार्ड की शीर्ष छतें; लागत सत्यापित होने तक रोकी गई"],
    f2h: "एक मिनट में रूफटॉप सोलर जाँचें",
    f2p: "छत का क्षेत्रफल और मासिक यूनिट दें। अनुशंसित सिस्टम आकार, नीति संस्करण और स्रोत सहित पीएम सूर्य घर सब्सिडी, और लागत वापसी की सीमा पाएँ।",
    f2l: ["ग्रिड पर छत की रूपरेखा बनाकर क्षेत्रफल नापें", "सब्सिडी नीति-तथ्य है; उत्पादन और लागत वापसी अनुमान के रूप में चिह्नित", "PDF सारांश — आधिकारिक आवेदन नहीं"],
    f2Cap: "उदाहरण: 70 वर्ग मी छत, 400 यूनिट प्रति माह, डेमो टैरिफ़।",
    f3h: "भरोसेमंद अलर्ट, English और हिंदी में",
    f3p: "योजनाकार आधिकारिक चेतावनी दर्ज करते हैं और दो-व्यक्ति जाँच से सार्वजनिक सलाह स्वीकृत करते हैं। जनता देख सकती है कि क्या सक्रिय है, उसे सुन सकती है और सहायक से पूछ सकती है।",
    f3l: ["हीट-डोम संकेत पूर्वानुमान संकेत है, आधिकारिक चेतावनी नहीं", "सलाह प्रकाशित होने से पहले स्वीकृति ज़रूरी", "सहायक केवल वही संख्याएँ बताता है जो उसके उपकरणों ने लौटाईं"],
    trustH: "हर संख्या बताती है कि वह कहाँ से आई।",
    trustLead: "गर्मी और सोलर के निर्णयों पर बहस होती है। कूलरूफ प्रमाण साथ रखता है।",
    rules: [
      ["हर मान के साथ स्रोत", "मापा हुआ, व्युत्पन्न, अनुमानित, नीति, उपयोगकर्ता-प्रदत्त या अनुपलब्ध — स्रोत, तिथि और रिज़ॉल्यूशन के साथ।"],
      ["संकेतक, निदान नहीं", "भूमि और आवास संकेत संकेतक के रूप में चिह्नित हैं। अनुपलब्ध डेटा समझाया जाता है, खाली नहीं छोड़ा जाता।"],
      ["ईमानदार सीमाएँ", "सुबह के उपग्रह गुज़रने का सतह तापमान हवा का तापमान नहीं है, और इस पिक्सेल आकार पर अलग-अलग छतें नहीं पहचानी जा सकतीं।"],
    ],
    ctaH: "अपने शहर के सबसे गर्म वार्ड देखें।",
    ctaP: "ऐप डेमो शहर और कृत्रिम टैरिफ़ के साथ स्थानीय रूप से चलता है।",
    footA: "सहायता सारांश — आधिकारिक आवेदन नहीं। pmsuryaghar.gov.in पर आवेदन करें।",
    footB: "डेमो में कृत्रिम शहर और कृत्रिम टैरिफ़ का उपयोग हुआ है।",
    solarRows: [["सिस्टम", "3 kW"], ["सब्सिडी", "₹78,000"], ["लागत वापसी", "अनुमान सीमा"]],
    alertRows: [["आधिकारिक चेतावनी", "स्टाफ द्वारा दर्ज"], ["हीट-डोम संकेत", "पूर्वानुमान, चेतावनी नहीं"], ["सार्वजनिक सलाह", "स्वीकृत, ऑडियो सहित"]],
  },
};
