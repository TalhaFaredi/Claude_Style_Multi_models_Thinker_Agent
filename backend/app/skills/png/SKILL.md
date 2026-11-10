---
name: png
description: Create a readable PNG diagram, poster, or information card using the safe image renderer.
triggers: [png, diagram, poster, infographic]
modes: [planner]
formats: [png]
source: written for this app
---
Produce a JSON drawing object, without code fences, for the PNG output builder.
Use width and height between 256 and 3000, background as a CSS color, and an elements array.
Supported element types are text, rect, ellipse and line. Every element has x and y coordinates;
shapes and lines also have x2 and y2. Text has text, fill and size (8 to 160). Shapes have fill and stroke.
Keep labels short, leave generous margins, and place labels above or inside shapes with good contrast.
Use only these primitives. No scripts, external URLs, images, or executable drawing code.
Check that labels fit within the canvas and that arrows, comparisons and numbers reflect the user's request.
