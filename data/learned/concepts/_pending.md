# Concept candidates awaiting expert review

Machine-drafted candidates. A domain expert skims each block and either **approves** it
(move the block into `library.md`, flipping `status:pending` → `status:approved`) or
**deletes** it. Nothing here is reachable by `recall_concepts` — the retriever reads
`library.md` only.

**The queue is currently empty.**

Last cleared 2026-09-07: the three border-object candidates drafted on 2026-09-03 were
all promoted to `library.md` (`hab-border-object-exclusion`, `hab-border-count-correction`,
and `hab-border-paired-compartments` — adopted by Lukas and renamed
`lj-border-paired-compartments`). Promotion also admitted **haase** to the approved-source
list in `README.md`. The reviewer notes for that batch — the verbatim-citation audit
against the local corpus, the keyword df-budget table, and the retrieval measurements —
are preserved in the git history of this file (see commit `4fd333f` and its follow-up).
When drafting the next batch, read the **Keyword budget** section of `README.md` first.
