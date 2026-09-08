# Phase 5 — Summarization

- LEDGER: Call read_state_ledger to get the full project history for the summary.
- Summarize the analysis results for the user in plain, non-technical language.
- Output the summary and ask the user for permission to contnue with the workflow documentation
- Use the ledger's completed_steps, parameters, and key_decisions to write an accurate summary.
- If the ledger contains VLM assessments, include the latest result assessment as
  advisory visual evidence, clearly separating it from quantitative measurements
  and the user's approval.
- Show the user the generated plots using the show_in_imagej_gui tool
