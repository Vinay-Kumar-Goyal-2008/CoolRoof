/** One consistent stroke set (24px grid, 1.6 stroke, round caps), drawn for CoolRoof. */
import type { ReactNode } from "react";

function Svg({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}
type P = { size?: number };

export const IconOverview = (p: P) => <Svg {...p}><rect x="3.5" y="3.5" width="7" height="7" rx="1.6" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.6" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.6" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.6" /></Svg>;
export const IconMap = (p: P) => <Svg {...p}><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z" /><path d="M9 4v14M15 6v14" /></Svg>;
export const IconSun = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6" /></Svg>;
export const IconChat = (p: P) => <Svg {...p}><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 4v-4H5.5A1.5 1.5 0 0 1 4 14.5v-9Z" /></Svg>;
export const IconBell = (p: P) => <Svg {...p}><path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2H4.5l1.5-2Z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></Svg>;
export const IconConsole = (p: P) => <Svg {...p}><rect x="3.5" y="4.5" width="17" height="15" rx="2.2" /><path d="m7.5 10 3 2.5-3 2.5M13 15h3.5" /></Svg>;
export const IconSettings = (p: P) => <Svg {...p}><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></Svg>;
export const IconArrow = (p: P) => <Svg {...p}><path d="M7 17 17 7M9 7h8v8" /></Svg>;
export const IconArrowRight = (p: P) => <Svg {...p}><path d="M4.5 12h15M13.5 6l6 6-6 6" /></Svg>;
export const IconPlus = (p: P) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>;
export const IconFilter = (p: P) => <Svg {...p}><path d="M4 8h10M18 8h2M4 16h2M10 16h10" /><circle cx="16" cy="8" r="2" /><circle cx="8" cy="16" r="2" /></Svg>;
export const IconChevron = (p: P) => <Svg {...p}><path d="m6 9 6 6 6-6" /></Svg>;
export const IconCollapse = (p: P) => <Svg {...p}><rect x="3.5" y="4.5" width="17" height="15" rx="2.2" /><path d="M9.5 4.5v15M15.5 10l-2 2 2 2" /></Svg>;
export const IconMenu = (p: P) => <Svg {...p}><path d="M4 7h16M4 12h16M4 17h16" /></Svg>;
export const IconWarn = (p: P) => <Svg {...p}><path d="M12 4 3 19.5h18L12 4Z" /><path d="M12 10v4.2M12 17v.01" /></Svg>;
export const IconThermo = (p: P) => <Svg {...p}><path d="M10 14.5V5.5a2 2 0 1 1 4 0v9a4 4 0 1 1-4 0Z" /><path d="M12 9v7" /></Svg>;
export const IconPeople = (p: P) => <Svg {...p}><circle cx="9" cy="8.5" r="3" /><path d="M3.5 19c.5-3.2 2.7-5 5.5-5s5 1.8 5.5 5" /><path d="M16 6.2a3 3 0 0 1 0 5.6M17.5 14.4c1.7.6 2.7 2.2 3 4.6" /></Svg>;
export const IconBuilding = (p: P) => <Svg {...p}><path d="M5 20V5.5A1.5 1.5 0 0 1 6.5 4h7A1.5 1.5 0 0 1 15 5.5V20M15 10h3.5A1.5 1.5 0 0 1 20 11.5V20M3.5 20h17" /><path d="M8.5 8h3M8.5 12h3M8.5 16h3" /></Svg>;
export const IconGauge = (p: P) => <Svg {...p}><path d="M4.5 17a8 8 0 1 1 15 0" /><path d="m12 13 3.5-4" /></Svg>;
export const IconCross = (p: P) => <Svg {...p}><rect x="4" y="4" width="16" height="16" rx="3.5" /><path d="M12 8v8M8 12h8" /></Svg>;
export const IconFlame = (p: P) => <Svg {...p}><path d="M12 3c.5 3-2.5 4.5-2.5 8a2.5 2.5 0 0 0 5 0c1.5 1 3 3 3 5.2A5.5 5.5 0 0 1 12 21.5 5.5 5.5 0 0 1 6.5 16c0-3.6 3-5.6 4-8 .6-1.4 1.1-3 1.5-5Z" /></Svg>;
export const IconShield = (p: P) => <Svg {...p}><path d="M12 3.5 5 6v5.6c0 4.2 2.8 7.5 7 8.9 4.2-1.4 7-4.7 7-8.9V6l-7-2.5Z" /><path d="m9 12 2.2 2.2L15.5 10" /></Svg>;
export const IconCoin = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M14.8 9.2c-.5-.8-1.5-1.2-2.8-1.2-1.6 0-2.7.8-2.7 2s1 1.7 2.7 2c1.7.3 2.8.8 2.8 2s-1.2 2-2.8 2c-1.3 0-2.4-.5-2.9-1.4M12 6.5V8m0 8v1.5" /></Svg>;
export const IconCool = (p: P) => <Svg {...p}><path d="M3.5 11.5 12 4l8.5 7.5M6 10v9.5h12V10" /><path d="M12 12.5v4M10 14.5h4" /></Svg>;
export const IconSend = (p: P) => <Svg {...p}><path d="M20.5 3.5 10 14M20.5 3.5 14 20.5l-4-6.5-6.5-4 17-6.5Z" /></Svg>;
export const IconGlobe = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.4 3.6 5.2 3.6 8.5s-1.1 6.1-3.6 8.5c-2.5-2.4-3.6-5.2-3.6-8.5S9.5 5.9 12 3.5Z" /></Svg>;

/** Brand mark: a roof line with a heat gradient bar, no text. */
export function LogoMark({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true" focusable="false">
      <rect width="34" height="34" rx="9" fill="var(--accent)" />
      <path d="M8 17.5 17 9l9 8.5" fill="none" stroke="#1a0f08" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.5 15.5V25h13v-9.5" fill="none" stroke="#1a0f08" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 21.5h6" stroke="#1a0f08" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}
