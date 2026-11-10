---
name: web-page
description: Write the content of a single static web page (landing page, info page, one-pager).
triggers: [web page, webpage, website, landing page, html, one-pager, homepage]
modes: [simple, thinker, planner]
formats: [html]
source: inspired by https://github.com/anthropics/skills (frontend-design, web-artifacts-builder); rewritten for this app
---
The Output Builder turns your Markdown into a safe static page (no scripts run), so write Markdown:
- `#` page title, then a one-sentence promise of what the reader gets.
- `##` sections in the order a visitor needs them: what it is, who it is for, how it works, proof (numbers, examples), next step.
- Short paragraphs and bullet lists; every section scannable in five seconds.
- Plain, specific wording. No lorem ipsum, no "unlock your potential".
- End with one clear call to action sentence.
When the user asks for HTML code itself, write one self-contained file: semantic tags, CSS in a <style> block,
system font stack, max-width about 760px, good contrast, mobile-friendly, and no external scripts.
