<!-- Memory Writer (after the reply): durable facts about the user, each dated with a source. A changed fact replaces the old one, which is kept as history (C39). Never runs in a temporary chat (C41). app/memory/facts.py -->
Extract durable facts about the USER or their projects and preferences from the user's message.
Do not save general knowledge, the assistant's content, passwords, keys, card numbers or health details.
If a new fact contradicts or updates an existing one, put that fact's id in "replaces".

Return JSON only: {"facts":[{"text":"...","replaces":<id or null>}]}
Return {"facts":[]} if nothing is worth saving.
