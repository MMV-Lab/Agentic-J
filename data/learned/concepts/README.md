# Concept library (workflow heuristics)

A third tier of learned memory, alongside `pitfalls/` and `recipes/`. Where those
capture **procedural** knowledge proven by a green run ("this code worked", "this
error had this fix"), this tier captures **strategic** knowledge — the *why* and
*when* of choosing an image-analysis approach, the kind of thing an experienced
analyst carries in their head. It is meant to be injected at **planning time**
(supervisor / plugin_manager, workflow phase 2), not at coding time.

## Why this is separate from pitfalls/recipes
- **Proven by expertise, not by execution.** A script can run green and still use the
  wrong approach. Concepts therefore cannot be auto-minted from green runs the way
  recipes are — every entry must cite an external, authoritative source.
- **Cross-cutting.** One heuristic ("flatten uneven background before thresholding")
  applies across many plugins and tasks; a recipe is one script.
- **Language-agnostic.** Heuristics are about the analysis, not Groovy vs Python, so
  entries are not split per language.

## Provenance rule (hard requirement)
Every concept entry MUST carry a `SRC:` citation to an authoritative source. No
un-cited entries are admitted. This is what keeps the model from laundering its own
guesses into "expert wisdom". Current approved sources:
- **bioimagebook** — Bankhead, *Introduction to Bioimage Analysis*, https://bioimagebook.github.io
- **image.sc** — the Scientific Community Image Forum, https://forum.image.sc (accepted answers only)
- **senft2023** — Senft et al., *A biologist's guide to planning and performing quantitative bioimaging experiments*, PLoS Biol 2023, doi:10.1371/journal.pbio.3002167
- **schmied2024** — Schmied et al., *Community-developed checklists for publishing images and image analyses*, Nat Methods 2024, doi:10.1038/s41592-023-01987-9
- **reinke2024** — Reinke et al., *Understanding metric-related pitfalls in image analysis validation*, Nat Methods 2024, doi:10.1038/s41592-023-02150-0
- **davide** — internal domain expert (coworker) contributions and edits, made during the human review of this queue
- **lukas** — internal domain expert (project maintainer) contributions, authored directly rather than drafted and reviewed

Internal-expert sources (`davide`, `lukas`) are the one admitted exception to the
"external, authoritative source" rule: the citation is to a *named human who is
accountable for the claim*, which is what the rule is actually protecting against —
the model laundering its own guesses. An entry with no named source is still refused.

## Review workflow (human-in-the-loop)
Machine-drafted candidates land in `_pending.md`. A domain expert skims each one and
either approves it (move the block to `library.md`, or `CORE.md` for the always-inject
floor) or deletes it. The expert is a **reviewer, not an author** — drafting is cheap,
so effort goes into filtering. Nothing reaches the planner until approved.

## Files
- `_pending.md` — machine-drafted candidates awaiting expert review (START HERE).
- `library.md`  — approved, recall-searchable heuristics. *(created on first approval)*
- `CORE.md`     — approved always-injected floor (fixed, small). *(created on first approval)*

## Entry format
    <!--c:ID status:pending|approved src:bioimagebook chap:<path> modality:general|fluorescence task:<task> kw:alias1,alias2-->
    - **WHEN** <trigger situation>
      **DO**   <recommended approach>
      **WHY**  <one-line rationale>
      **AVOID** <the naive wrong move>
      SRC: <source> · <human-readable location>
