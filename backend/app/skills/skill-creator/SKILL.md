---
name: skill-creator
description: Help the user write a new SKILL.md for this app's Skills Hub.
triggers: [create a skill, new skill, write a skill, skill.md, skill file, add a skill]
modes: [simple, thinker, planner]
source: inspired by https://github.com/anthropics/skills (skill-creator skill); rewritten for this app's skill format
---
A skill is the folder `backend/app/skills/<name>/` with one SKILL.md:
1. Front matter between --- lines: name (kebab-case), description (one line), triggers (words that make it relevant),
   modes (simple, thinker, planner), formats (optional: pdf, html, md, code, text, plan), source (credit).
2. Body: 5 to 10 short, concrete instructions, under 200 words, since every word costs tokens on each use.
Write triggers the user would really type, and avoid very common words, or the skill loads too often.
Write instructions as actions ("Start with the verdict"), not virtues ("Be clear").
Show the full SKILL.md in one code block, then one example question that would trigger it.
