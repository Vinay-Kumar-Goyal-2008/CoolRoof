"use client";

import { SignalsPanel } from "@/components/SignalsPanel";
import { useAppData } from "@/lib/data";
import { useI18n } from "@/lib/i18n";

export default function AlertsPage() {
  const { t } = useI18n();
  const { wards } = useAppData();
  return (
    <>
      <header className="pagehead"><h1 className="display">{t("pageSignals")}</h1></header>
      <SignalsPanel wards={wards.data} />
    </>
  );
}
