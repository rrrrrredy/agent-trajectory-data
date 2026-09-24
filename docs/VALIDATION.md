# Validation

## Version 0.2 — 2026-09-24

44 automated tests passed on Windows with Python 3.11. Provider unit tests use explicit mocked CLI event fixtures; they are not live model execution evidence.

The separate live batch used the existing local Codex login, requested model gpt-6-astra, and Codex CLI 0.155.0-alpha.16.3:

| Synthetic variant | Observed adapter calls | Deterministic result |
| --- | ---: | --- |
| Available source | 2 | Pass |
| Missing source | 2 | Pass |
| Transient 429 then success | 3 | Pass |

Three diagnostic records were exported; zero SFT records were exported because the configured output policy permits diagnostics only. Total returned input tokens: 76,725, including 8,320 cached input tokens; output tokens: 444. Billing amount and authoritative returned model version remain unknown.

The same completed batch was invoked again. The persisted reservation count and capture-file count both stayed at seven; no completed task was executed again.

A separate one-call integration probe preceded this batch. Its model action returned, but an informational CLI startup item caused the strict parser to label the probe as a protocol failure. The original capture remains unchanged. Its visible event stream reports 10,880 input and 58 output tokens; these are not included in the successful batch totals.

Tests additionally cover durable budget admission, interrupted-call recovery without reissue, exclusive worker locking, frozen batch config, secret-free provider config, host-input/capture/action binding, model output-use restrictions, token metadata integrity, and omission of reasoning events.

These results establish observed model calls in a small controlled environment and local pipeline behavior. They do not establish general research quality, commercial rights for model outputs, training gains, revenue, or a production service.

## Version 0.1 — historical control validation

29 automated tests passed. Eight synthetic families produced 24 tasks and 72 scripted control runs: 24 correct submissions, 24 incorrect submissions, and 24 step-budget terminations with no assessed answer.

Diagnostic export accepted 72; default SFT export accepted zero. The workflow-import test used a constructed metadata fixture. No private historical workflow was imported in that control execution.
