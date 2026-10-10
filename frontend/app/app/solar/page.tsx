"use client";

import { SolarCard } from "@/components/SolarCard";
import { useI18n } from "@/lib/i18n";

export default function SolarPage() {
  const { t } = useI18n();
  return (
    <>
      <header className="pagehead"><h1 className="display">{t("pageSolar")}</h1></header>
      <div className="narrow"><SolarCard /></div>
    </>
  );
}
