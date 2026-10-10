import type { Envelope, ValueClass } from "@/lib/api";
import { fmt } from "@/lib/i18n";

const LABEL: Record<ValueClass, string> = {
  measured: "measured", derived: "derived", estimated: "estimated", policy: "policy",
  user: "user", unavailable: "unavailable", stale: "stale",
};

/** A number with its provenance class; source, date and resolution show on hover/focus. */
export function Badge({ env, unit = "", digits = 1 }: { env?: Envelope; unit?: string; digits?: number }) {
  if (!env) return <span className="num">—</span>;
  const title = [
    `source: ${env.source}`,
    env.observed ? `observed: ${env.observed}` : null,
    env.processed ? `processed: ${env.processed}` : null,
    env.resolution_m ? `resolution: ${env.resolution_m} m` : null,
    env.reason ? `reason: ${env.reason}` : null,
    env.assumptions?.length ? `assumptions: ${env.assumptions.join(", ")}` : null,
  ].filter(Boolean).join("\n");
  const value = typeof env.value === "number" ? fmt(env.value, digits) : (env.value ?? "—");
  return (
    <span className="badge-wrap" tabIndex={0} title={title}>
      <span className="num">{value}{unit && ` ${unit}`}</span>
      <span className={`badge badge-${env.class}`}>{LABEL[env.class]}</span>
    </span>
  );
}

export function ClassTag({ cls }: { cls: string }) {
  return <span className={`badge badge-${cls.toLowerCase()}`}>{cls}</span>;
}
