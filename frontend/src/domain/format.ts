/** Money for people. Real prices are tiny, so never round them to a misleading "$0.00": $0.25, $0.0034, $0.00005. */
export function money(v: number): string {
  if (!Number.isFinite(v)) return "Price unknown";
  if (v === 0) return "$0";
  if (v >= 0.01) return `$${v.toFixed(2)}`;
  const s = v.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
  return `$${s === "0" ? "0.00001" : s}`;
}

/** Show tiny per-call/model-band charges without rounding them up to one cent. */
export function preciseMoney(v: number): string {
  if (!Number.isFinite(v)) return "Price unknown";
  if (v <= 0) return money(v);
  const digits = v.toFixed(v >= 1 ? 4 : v >= 0.01 ? 6 : 8).replace(/0+$/, "").replace(/\.$/, "");
  return digits === "0" ? "<$0.00000001" : `$${digits}`;
}

export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

let counter = 0;
/** Short unique id for client-side messages. */
export function uid(prefix = "m"): string {
  counter += 1;
  return `${prefix}${Date.now().toString(36)}${counter.toString(36)}`;
}
