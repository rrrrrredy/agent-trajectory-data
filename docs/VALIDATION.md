# Local validation

Validated on 2026-09-24 using Python 3.11.

- 29 automated tests passed.
- End-to-end CLI execution generated 8 synthetic families and 24 tasks.
- Three scripted policies produced 72 observed control runs: 24 correct submissions, 24 incorrect submissions, and 24 step-budget terminations with no assessed answer.
- Diagnostic export: 72 accepted, 0 quarantined.
- Default SFT export: 0 accepted, 72 quarantined, as expected for scripted controls.
- The final quality rules were also checked against all 72 stored runs.

Tests cover evidence grounding, abstention, retries, timeout handling, failure retention, invalid model identity, task/event association, corrupted records, path boundaries, immutable artifacts, split integrity, and training exclusions.

The import test uses a constructed review-metadata fixture. No private historical workflow was imported in this end-to-end run.

No model API was called. These results establish local control behavior, not real model quality, general semantic grading accuracy, revenue, or production reliability.
