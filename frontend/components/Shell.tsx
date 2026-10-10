"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAppData } from "@/lib/data";
import { useI18n, type Key } from "@/lib/i18n";
import {
  IconBell, IconChat, IconChevron, IconCollapse, IconConsole, IconMap, IconMenu, IconOverview, IconSettings, IconSun, LogoMark,
} from "./Icons";

const NAV: { href: string; label: Key; icon: React.ReactNode; group: "w" | "t" }[] = [
  { href: "/app", label: "tabOverview", icon: <IconOverview />, group: "w" },
  { href: "/app/heat", label: "tabHeat", icon: <IconMap />, group: "w" },
  { href: "/app/solar", label: "tabSolar", icon: <IconSun />, group: "w" },
  { href: "/app/assistant", label: "tabAssistant", icon: <IconChat />, group: "w" },
  { href: "/app/alerts", label: "tabSignals", icon: <IconBell />, group: "t" },
  { href: "/app/console", label: "tabConsole", icon: <IconConsole />, group: "t" },
];

export function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="lang" role="group" aria-label="Language">
      <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
      <button type="button" aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>हिं</button>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const { wards, alerts } = useAppData();
  const nWards = wards.data?.wards.length;
  const nAlerts = alerts.data?.alerts.length ?? 0;
  const active = NAV.find((n) => n.href === path) ?? NAV[0];
  const official = wards.data?.signals.official_warning;
  const synced = wards.data?.scenes?.[0]?.date ?? "—";

  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const counts: Record<string, string | number | undefined> = {
    "/app/heat": nWards,
    "/app/alerts": nAlerts > 0 ? nAlerts : undefined,
  };

  const group = (g: "w" | "t") => (
    <div className="navgroup">
      <span className="label">{t(g === "w" ? "grpWorkspace" : "grpTools")}</span>
      <div className="nav">
        {NAV.filter((n) => n.group === g).map((n) => (
          <Link key={n.href} href={n.href} aria-current={n.href === path ? "page" : undefined}>
            {n.icon}
            <span>{t(n.label)}</span>
            {counts[n.href] !== undefined && <span className="count">{counts[n.href]}</span>}
          </Link>
        ))}
      </div>
    </div>
  );

  return (
    <div className="shell">
      <aside className={`sidebar${open ? " open" : ""}`} id="sidebar" aria-label="Primary">
        <Link href="/" className="brand" aria-label={`${t("appTitle")} — ${t("backHome")}`}>
          <LogoMark />
          <div>
            <b>{t("appTitle").toUpperCase()}</b>
            <span>{t("brandSub")}</span>
          </div>
        </Link>
        <div className="switcher">
          <span className="ini" aria-hidden="true">CR</span>
          <p>
            <b>{t("cityName")}</b>
            <br />
            <span className="sub">{nWards ?? "—"} {t("activeWards")}</span>
          </p>
          <IconChevron size={16} />
        </div>
        {group("w")}
        {group("t")}
        <div className="grow" />
        <div className="synccard">
          <p><span className="dot good" aria-hidden="true" />{t("localLive")}</p>
          <span className="mono">{t("lastSync")} · {synced}</span>
        </div>
        <div className="nav" style={{ marginTop: 10 }}>
          <Link href="/app/console"><IconSettings /><span>{t("settings")}</span></Link>
        </div>
        <div className="usercard">
          <span className="ini" aria-hidden="true">CP</span>
          <p><b>Planner</b><br /><span className="sub">{t("userRole")}</span></p>
          <button type="button" aria-label={t("closeMenu")} onClick={() => setOpen(false)}><IconCollapse /></button>
        </div>
      </aside>
      <div className={`scrim${open ? " open" : ""}`} onClick={() => setOpen(false)} aria-hidden="true" />

      <div className="main">
        <header className="topbar">
          <button type="button" className="iconbtn menu-btn" aria-label={t("menu")} aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(true)}>
            <IconMenu />
          </button>
          <nav className="crumbs" aria-label="Breadcrumb">
            <span>{t("crumbRoot")}</span><i aria-hidden="true">/</i><b>{t(active.label)}</b>
          </nav>
          <div className="sp" />
          <span className="updated">{t("lastUpdated")} {synced}</span>
          <LangToggle />
          <Link href="/app/alerts" className="btn iconbtn" aria-label={t("notifications")}>
            <IconBell />
            {nAlerts > 0 && <span className="pip" aria-hidden="true" />}
          </Link>
          <span className="userchip"><span className="ini" aria-hidden="true">CP</span><span>Planner</span><IconChevron size={16} /></span>
        </header>
        <div className="page">
          {official && path !== "/app/alerts" && (
            <aside className="banner official" role="status" style={{ marginBottom: 20 }}>
              <strong>{t("officialWarning")}: {official.level.toUpperCase()}</strong> · {official.issued_by} · {official.valid_until.slice(0, 10)} — {official.text}
            </aside>
          )}
          {children}
        </div>
        <footer className="foot muted small">{t("disclaimer")} · {t("syntheticNote")}</footer>
      </div>
    </div>
  );
}
