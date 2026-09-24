# Changelog

## 0.2.0

- Add an observed Codex CLI provider that captures task inputs, visible events, session IDs, requested model configuration, returned usage, and failures.
- Bind model actions and usage to capture files during quality checks, with a separate model-output-use policy.
- Add finite automatic production batches with durable admission, exclusive worker locks, frozen configuration, and restart handling without reissuing unknown calls.
- Embed visible model-call records in diagnostic exports and scope exports to the current batch.
- Complete a live three-task batch using seven adapter calls; verify a repeated invocation makes no new calls.
- Expand the automated suite to 44 passing tests.
- Keep raw data and model events out of Git; retain private-only distribution and proprietary licensing.

## 0.1.0

Initial local synthetic-task controls, visible event traces, deterministic graders, failure retention, family splits, and gated exports.
