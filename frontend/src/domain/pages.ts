/** One-based page ranges, validated before an estimate or paid read is requested. */
export function parsePageSelection(value: string, total: number): { pages?: number[]; error: string } {
  if (!value.trim()) return { error: "" };
  const pages = new Set<number>();
  for (const part of value.split(",")) {
    const match = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
    if (!match) return { error: "Use page numbers or ranges, such as 1-3, 7." };
    const start = Number(match[1]), end = Number(match[2] ?? match[1]);
    if (start < 1 || end < start || end > total) return { error: `Pages must be between 1 and ${total}, in ascending ranges.` };
    for (let page = start; page <= end; page++) pages.add(page);
  }
  return { pages: [...pages].sort((a, b) => a - b), error: "" };
}
