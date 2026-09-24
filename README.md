# Agent Trajectory Data

Private, proprietary pipeline for agent execution trajectories and evaluation data. Production decisions are automatic: validate, accept, quarantine, or stop within a budget. There is no human annotation or review queue.

Version 0.2 connects the local control environment to **observed Codex CLI model calls**, retains visible events and token usage, and runs finite batches with durable call admission and restart protection.

[中文运行说明](docs/RUN.zh-CN.md) · [产品与架构方案](docs/PLAN.zh-CN.md) · [Protocol](docs/PROTOCOL.md) · [Validation](docs/VALIDATION.md)

## Run a complete batch

Python 3.10+; runtime uses the standard library. Run from this repository:

```powershell
# Offline scripted controls
py -3 -B -m agentdata --root data/control-v0.2 pipeline --config configs/control.json --batch-id control-001

# Real model decisions using the existing Codex CLI login
py -3 -B -m agentdata --root data/model-v0.2 pipeline --config configs/codex-local.json --batch-id model-001

# Run this same command again to resume; completed tasks are not called again.
py -3 -B -m agentdata --root data/model-v0.2 pipeline --config configs/codex-local.json --batch-id model-001

py -3 -B -m unittest discover -s tests -v
```

The model configuration explicitly requests `gpt-6-astra`; it is not a claim about the latest model or a returned version. The real batch was tested with Codex CLI 0.155.0-alpha.16.3. Other versions may require an adapter update.

A model batch requires a working local Codex login. Authentication stays with the CLI; the repository does not read or copy credentials. The shipped config allows at most 8 adapter calls, 90 seconds per task, and 600 seconds per batch. These are **CLI invocation and wall-time limits**, not a billable-dollar cap or a count of the CLI's internal transport retries.

Outputs are under `<root>/batches/<batch-id>/`: state, summary, diagnostic export, and SFT export. Requests and captured events are under `<root>/runs/<run-id>/model_calls/`. Raw data and exports stay outside Git.

## Implemented

- Synthetic fact tasks covering available evidence, terminal missing sources, and transient 429 failures.
- Scripted controls and actual observed model decisions against the same environment.
- Visible task inputs, model action messages, tool results, terminal outcomes, and immutable task snapshots.
- Separate pass, fail, and not-assessed outcomes; first failures remain intact.
- Deterministic grading and export regrading, source/evidence checks, family splits, hash/chain checks, and quarantine.
- Model request configuration, CLI session identity, original emitted visible events, actual returned usage, and action binding.
- Durable admission before model calls; a single-worker OS lock; no automatic reissue of an interrupted unknown request.
- A complete finite batch from generation through private exports in one command.
- A narrow importer for existing Research Toolkit review metadata; those incomplete imports remain quarantined.

## Data and product boundaries

A synthetic task executed by a model is labeled as a synthetic task with observed model execution. Scripted controls and imported metadata have separate labels.

The CLI does not return an authoritative model version or billing amount here. Those values remain unknown. The recorded request is the host's task input, not a dump of Codex's internal system context. Capture integrity checks establish local consistency, not cryptographic provider attestation.

The shipped model-output policy permits local diagnostics only, so the real batch's SFT export is empty. The SFT gate can accept a consistent successful non-holdout model run only when its configured task and output policies allow that use. A config flag does not itself create legal rights.

The diagnostic package is private and may contain answers for holdout families. It is not a public benchmark or a complete resettable evaluation release.

Remaining work includes broader actual-business-task capture, other model providers, monetary reservation/settlement, complete environment packaging, stronger privacy filters, unattended recurring operation, and commercial delivery/payment. The current command runs a finite unattended batch; it does not install an always-on service or establish sales or training gains.
