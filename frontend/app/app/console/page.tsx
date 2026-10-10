"use client";

import { PlannerConsole } from "@/components/PlannerConsole";
import { useAppData } from "@/lib/data";
import { useI18n } from "@/lib/i18n";

export default function ConsolePage() {
  const { t } = useI18n();
  const { wards, selected } = useAppData();
  return (
    <>
      <header className="pagehead"><h1 className="display">{t("pageConsole")}</h1></header>
      <PlannerConsole wards={wards.data} selected={selected} />
    </>
  );
}
