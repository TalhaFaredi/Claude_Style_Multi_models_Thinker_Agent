import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown } from "@/components/chat/Markdown";

describe("safe answer rendering", () => {
  it("renders headings and scrollable tables as native elements", () => {
    const html = renderToStaticMarkup(createElement(Markdown, { text: "# Facts\n\n| Name | Value |\n| --- | --- |\n| Budget | $20 |" }));
    expect(html).toContain('role="heading"');
    expect(html).toContain('<table>');
    expect(html).toContain('table-scroll');
    expect(html).toContain('<td>$20</td>');
  });
  it("escapes HTML and refuses executable links while keeping HTTPS sources usable", () => {
    const html = renderToStaticMarkup(createElement(Markdown, { text: '<script>alert(1)</script>\n\n[bad](javascript:alert) [source](https://example.org/fact)' }));
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('href="javascript:');
    expect(html).toContain('href="https://example.org/fact"');
  });
});
