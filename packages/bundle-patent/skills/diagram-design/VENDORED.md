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
- Keep patent-specific edits out of SKILL.md and `references/`; patent-specific rules live in the
  [patent-figure-design](../patent-figure-design/SKILL.md) skill, which routes to this one
  and ships the CNIPA monochrome profile (`patent-figure-design/assets/cnipa-monochrome.md`)
  that overrides the editorial default skin for patent figures.
