---
name: workflow-documentation
description: Use this skill to generate workflow documentation for ImageJ/Fiji projects.
---
 

Write a pre-filled documentation template of the documentation workflow. 
Leave fields as [TO BE FILLED] only when you genuinely cannot infer the value from the project files.
Follow the structure below, using information from script descriptions, result files, and any other relevant project files to fill in as much detail as possible.


# Workflow Documentation
**Project name:** [extracted from folder name]
**Date:** [today's date]
**Workflow type:** New Workflow

---

## 1. Scientific Goal
[Describe what biological question this workflow addresses, inferred from script descriptions and result files]

## 2. Software Components & Versions

You can find software versions in the [project_root]/logs/environment_metadata.log file. 

| Component | Version | Role |
|-----------|---------|------|
| ImageJ/Fiji | [extract if found, else TO BE FILLED] | Image processing |
| Python | [extract if found, else TO BE FILLED] | Statistical analysis |
| [library] | [version] | [role] |

## 3. Processing Sequence
Describe each step in order:
1. [Step name] — [what it does, key parameters]
2. ...

## 4. Key Settings & Parameters
| Parameter | Value | Script | Rationale |
|-----------|-------|--------|-----------|
| [e.g. Threshold method] | [e.g. Otsu, value=X] | [script name] | [why chosen, if documented] |

## 5. Input Data
- **Image type:** [e.g. fluorescence microscopy, brightfield]
- **Format:** [e.g. TIFF, 16-bit, multi-channel]
- **Location:** [raw_images/ subfolder or user-provided path]

## 6. Output Data
- **Results CSV:** [filename and location]
- **Statistics CSV:** [Statistics_Results.csv location]
- **Figures:** [list figures generated, 300 DPI PNG/SVG]

## 7. Statistical Analysis
- **Test(s) used:** [e.g. Mann-Whitney U, Shapiro-Wilk normality test]
- **Significance threshold:** [e.g. p < 0.05]
- **Outlier handling:** [e.g. IQR method, threshold = 1.5]

## 8. Manual Steps (ROI / User Verification)
[Describe any steps that required manual user input, such as ROI selection or parameter approval]

## 9. Rationale
[Explain why each major method choice was made — inferred from script descriptions]

## 10. Limitations & Known Issues
[List any limitations documented in script descriptions or failure logs]

## 11. Reproducibility
- **Code location:** scripts/ subfolder
- **Example data:** [TO BE FILLED — add path or repository URL]
- **Public access:** [TO BE FILLED — add DOI, GitHub URL, or Zenodo link]
- **Container / install:** [TO BE FILLED — add Dockerfile or requirements.txt path]


CRITICAL : Save Workflow_Documentation.md to: [project_root]/Workflow_Documentation.md using the 'save_markdown' tool

PHASE 7: AUTOMATIC QA DOCUMENTATION (MANDATORY)

This phase runs automatically after Phase 5 (Summarization) for every project.
It is non-negotiable and cannot be skipped.

1. TRIGGER: After confirming all results are saved and the user summary is complete,
  call the `qa_reporter` subagent.

2. INPUT: Pass the absolute path to the project root folder, e.g.:
  "Please audit the project at /app/data/project_name/"

3. WAIT for qa_reporter to return the path to the  generated file:
  - QA_Checklist_Report.md

4. NOTIFY THE USER with a brief, non-technical summary such as:
  "I've completed the QA audit for this project. Here's what was found:
  - X out of Y required items passed.
  - [List any ❌ FAIL items in plain language, one sentence each]
  The full checklist and documentation template have been saved to your project folder."

5. If any MINIMAL items FAILED, explicitly tell the user:
  "Before publishing, the following are required: [list items]"

6. Do NOT expose the raw markdown to the user. Summarize it in plain language.

NOTE: The qa_reporter works autonomously. Do not interrupt it or ask the user
for input during this phase.