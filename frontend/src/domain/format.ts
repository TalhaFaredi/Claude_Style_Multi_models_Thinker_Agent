/** Money for people. Real prices are tiny, so never round them to a misleading "$0.00": $0.25, $0.0034, $0.00005. */
export function money(v: number): string {
  if (v === 0) return "$0";
  if (v >= 0.01) return `$${v.toFixed(2)}`;
  const s = v.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
  return `$${s === "0" ? "0.00001" : s}`;
}

export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

let counter = 0;
/** Short unique id for client-side messages. */
export function uid(prefix = "m"): string {
  counter += 1;
  return `${prefix}${Date.now().toString(36)}${counter.toString(36)}`;
}
