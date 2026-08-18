"""PARKED — do not import from production code paths.

Structured-template experiment (2026-08-14) that we chose NOT to ship.
Files (`schema.py`, `minimal.py`) kept as reference. Rendered output was
worse than the existing free-text `core.resume.writer.render_docx`. If
you find yourself tempted to revive this, read the "Decisions log" in
`.claude/projects/.../memory/project_jobot_profile_hub.md` first — the
free-text path already works, and the LLM produces cleaner sections than
a hand-crafted structured render.

Fallback for bad-looking resumes: add a "Regenerate cleanly" button in
the Profile preview UI (Phase 2). Not a new template.
"""

