---
name: supervisor_pipeline_phases
description: >
  Detailed step-by-step instructions for each phase of the ADVANCED analysis pipeline.
  The supervisor MUST read the relevant phase file BEFORE entering that phase.
  Advanced (multi-phase study) follows the sequence
  1(gather) → 2(plan) → 3(setup) → 4a(io) → 4b(process) →
  4c(stats) → 4d(plot) → 5(summarize) → 6(document) → 7(qa).
  A single self-contained operation is not a study — it is handled by quick mode
  (set_mode("quick")), not by these phases.
---

## File Index

| File | When to Load |
|------|-------------|
| `phase_1_gathering.md` | Start of every new project |
| `phase_2_planning.md` | After Phase 1, before proposing pipelines |
| `phase_3_setup.md` | After user approves pipeline |
| `phase_4a_io_check.md` | Before any image processing |
| `phase_4b_processing.md` | For each processing step |
| `phase_4c_statistics.md` | After all processing complete |
| `phase_4d_plotting.md` | After Statistics_Results.csv confirmed |
| `phase_5_summarization.md` | After all figures generated |
| `phase_6_documentation.md` | Before QA |
| `phase_7_qa.md` | Final step |

