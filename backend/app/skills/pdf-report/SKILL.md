---
name: pdf-report
description: Structure a report or brief that becomes a PDF or Markdown file.
triggers: [report, pdf, whitepaper, brief, briefing, handout]
modes: [simple, thinker, planner]
formats: [pdf, md, txt]
source: inspired by https://github.com/anthropics/skills (pdf skill); rewritten for this app's PDF builder
---
The Output Builder turns Markdown into the file, so write clean Markdown:
- One `#` title. Then `##` sections, `###` only when a section really needs parts.
- Start with a 3 to 5 line summary of the main findings.
- Usual order: Summary, Background, Findings (one `##` per topic), Recommendations, Sources.
- Use bullet lists for parallel items and keep paragraphs to 2 to 5 sentences.
- Put every number with its unit and year. Name the source next to the fact, then list all sources at the end.
- Use **bold** only for key terms, never for whole sentences. No emoji, no HTML.
- For a "2-page" report aim for about 700 to 900 words. For "1 page", about 400.
