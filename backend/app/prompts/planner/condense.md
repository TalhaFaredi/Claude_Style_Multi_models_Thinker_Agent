<!-- Planner output step: the rendered PDF ran over the requested page count even with smaller type.
     app/modes/planner/steps.py (_condense). Values: $pages (requested pages), $words (hard word limit). -->
Rewrite the document so it fits on exactly $pages page(s) as a PDF: use AT MOST $words words in total.
Keep the title, a few short headings, every number, name and source reference that matters, and the conclusion. Cut repetition, filler, long tables and the least important points first. Do not add new facts.
Return only the shortened document in Markdown, with no comments before or after it.
