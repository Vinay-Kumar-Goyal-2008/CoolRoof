"use client";

import { ChatPanel } from "@/components/ChatPanel";
import { useAppData } from "@/lib/data";
import { useI18n } from "@/lib/i18n";

export default function AssistantPage() {
  const { t } = useI18n();
  const { selected } = useAppData();
  return (
    <>
      <header className="pagehead"><h1 className="display">{t("pageAssistant")}</h1></header>
      <div className="narrow"><ChatPanel wardId={selected} /></div>
    </>
  );
}
