import { Fragment, type ReactNode } from "react";

/** Model content stays React text; HTML and executable URL schemes are never rendered. */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^\s)]+\))/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    const link = part.match(/^\[([^\]]+)\]\(([^\s)]+)\)$/);
    if (link) {
      try {
        const url = new URL(link[2]);
        if (url.protocol === "https:" || url.protocol === "http:") return <a key={i} href={url.href} target="_blank" rel="noopener noreferrer">{link[1]}</a>;
      } catch { /* Render invalid and relative URLs as text. */ }
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

const cells = (line: string) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((v) => v.trim());
export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  for (let i = 0; i < lines.length;) {
    const key = i;
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.startsWith("```")) {
      const language = line.slice(3).trim();
      const body: string[] = [];
      for (i++; i < lines.length && !lines[i].startsWith("```"); i++) body.push(lines[i]);
      i++;
      blocks.push(<pre key={key} className="code-block" aria-label={language ? `${language} code` : "Code"}><code>{body.join("\n")}</code></pre>);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) { blocks.push(<div key={key} role="heading" aria-level={Math.min(6, heading[1].length + 1)} className="markdown-heading">{inline(heading[2])}</div>); i++; continue; }
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
      const headers = cells(line);
      const rows: string[][] = [];
      for (i += 2; i < lines.length && lines[i].includes("|") && lines[i].trim(); i++) rows.push(cells(lines[i]));
      blocks.push(<div key={key} className="table-scroll" tabIndex={0} role="region" aria-label="Answer table"><table><thead><tr>{headers.map((cell, n) => <th key={n}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row, r) => <tr key={r}>{row.map((cell, n) => <td key={n}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const list = line.match(/^\s*(?:([-*])|(\d+)\.)\s+(.+)$/);
    if (list) {
      const ordered = !!list[2];
      const items: ReactNode[] = [];
      for (; i < lines.length; i++) {
        const item = lines[i].match(ordered ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-*]\s+(.+)$/);
        if (!item) break;
        items.push(<li key={i}>{inline(item[1])}</li>);
      }
      blocks.push(ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>);
      continue;
    }
    const body = [line];
    for (i++; i < lines.length && lines[i].trim() && !/^(?:```|#{1,6}\s|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i]); i++) {
      if (i + 1 < lines.length && lines[i].includes("|") && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) break;
      body.push(lines[i]);
    }
    blocks.push(<p key={key}>{inline(body.join("\n"))}</p>);
  }
  return <>{blocks}</>;
}
