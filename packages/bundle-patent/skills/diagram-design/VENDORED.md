# Vendored skill

This directory is a vendored copy of [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design)
`skills/diagram-design/` (MIT, see [LICENSE](LICENSE)), vendored into the patent bundle so the
patent assistant can draw figure types the three drawio-native shapes do not cover
(sequence, state machine, deployment, and the rest of the 40 types).

- Vendored at upstream skill version 2.6 (repo cloned 2026-09-16).
- Keep upstream content unchanged except for the deviations recorded below. Update from upstream, then re-apply those deviations.
- Local deviations from upstream (re-apply after every update):
  - Trailing whitespace stripped on `references/onboarding.md:84` and
    `assets/example-queue-animated.html:298` — upstream ships both lines with
    trailing spaces and the repository whitespace gate rejects them.
  - Documentation links: correct the quadrant scenario-matrix anchor in
    `SKILL.md` to GitHub's heading slug and add explicit `url`, `skill`, and
    `folder` anchors to `references/onboarding.md` for its existing navigation links.
  - SKILL.md description rewritten to state trigger scenarios ("Use when the user
    asks to create/draw/redraw a diagram…") and to put the output form within the
    first 250 characters — upstream ships a bare capability list with no routing
    cues, so the router cannot tell when to load the skill.
  - SKILL.md body kept under the 500-line budget by sinking verbatim content:
    §7 per-type complexity budget → `references/complexity-budget.md` (new file),
    §8 summary-card pattern and the dotted-paper variant → `references/output-spec.md`
    §§ 7–8, and the Google Fonts `<link>` snippet → pointer to
    `references/style-guide.md` § Font stack (which already ships the snippet).
  - Vendored-path convergence: upstream's `<repo-root>/scripts/verify-geometry.py`
    and `verify-motion.py` references (§6 rule 6, §9 checklist) don't exist in this
    copy — rewritten to the bundled `scripts/self_check.py` plus visual checks.
    `references/export-registry.md` (`--registry` block-registry exports) linked
    from §12 Exporting so the entry point is reachable. A 🔴 marker added to the
    "Confirm before drawing" heading.
  - SKILL.md failure-mode fallbacks added: unparsable `.diagram-design` marker →
    fall through to the markerless gate path; `self_check.py` failure → fix the
    reported items and rerun; import sources that fail to extract (encrypted,
    corrupted, oversized) → report and ask for a re-export, never guess; unreachable
    Google Fonts → keep the family stack and let the browser fall back; §9 six
    connector-rule checklist lines compressed to one §6 pointer carrying the
    verify-geometry (repo checkout) / visual-check (installed skill) split;
    `references/doctor.md` linked from §0.
- Keep patent-specific edits out of SKILL.md and `references/`; patent-specific rules live in the
  [patent-figure-design](../patent-figure-design/SKILL.md) skill, which routes to this one
  and ships the CNIPA monochrome profile (`patent-figure-design/assets/cnipa-monochrome.md`)
  that overrides the editorial default skin for patent figures.
