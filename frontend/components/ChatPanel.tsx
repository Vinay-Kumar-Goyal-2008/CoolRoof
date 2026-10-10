"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface Msg { role: "user" | "assistant"; text: string; pdf?: string | null; grounded?: boolean }

export function ChatPanel({ wardId }: { wardId: string | null }) {
  const { t, lang } = useI18n();
  const [session, setSession] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { api.session().then((s) => setSession(s.session_id)).catch(() => undefined); }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs]);

  async function send() {
    const message = text.trim();
    if (!message || !session || busy) return;
    setText("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: message }]);
    try {
      const r = await api.chat(session, message, lang, wardId ?? undefined);
      setMsgs((m) => [...m, { role: "assistant", text: r.reply, pdf: r.pdf_url, grounded: r.grounded }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `${t("error")}: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card chat">
      <p className="muted">{t("assistantHint")}</p>
      <div className="msgs" role="log" aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            <p>{m.text}</p>
            {m.pdf && <a href={`/api${m.pdf}`} target="_blank" rel="noreferrer">{t("downloadPdf")}</a>}
            {m.role === "assistant" && m.grounded && <span className="muted small">✓ numbers checked against tool results</span>}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={t("typeMessage")}
               aria-label={t("typeMessage")} maxLength={2000} />
        <button type="submit" disabled={busy || !session}>{t("send")}</button>
      </form>
    </section>
  );
}
