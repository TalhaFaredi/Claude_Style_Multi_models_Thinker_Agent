---
name: output-format
description: Shape the answer in the format the user asked for (table, list, JSON, CSV, outline).
triggers: [markdown, json, csv, checklist, as a table, in a table, bullet points, columns, comparison table]
hints: [table, format, bullet, bullets, list, outline]
modes: [simple, thinker, planner]
formats: [text, md]
source: written for this app (spec Part 1, Skills Hub - output format)
---
- Use exactly the format asked for. If none is asked, use short paragraphs, and lists only for real lists.
- Tables: a header row, one idea per column, units in the header, no empty cells (write "n/a").
- JSON or CSV: output only valid data inside one code block, no comments, consistent keys, no trailing commas.
- Checklists: one action per line, starting with a verb.
- Outlines: at most 3 levels, parallel wording at each level.
- Put the direct answer first. Keep headings only when the answer is longer than about 200 words.
