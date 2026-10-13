# Runtime dataset protocol

Existing and future user tasks, development tasks, reference tests and cases are real independent tasks; tests actually executed are real tests. Task identity follows the research question, so repeated runs of one task remain repeated runs. Source materials retain their stated provenance, including supplied or constructed data. Astra in a separate context can review independently; no outside person, different model vendor or additional external material is required. Changes to task assignment, reviewer inputs or acceptance criteria require targeted revalidation.

Current implementation: v0.11 research workspace tasks, pending full model collection and release acceptance. The latest fully published package remains v0.10. See [current plan](PLAN.zh-CN.md) and [batch construction](BUILDING-BATCHES.zh-CN.md).

The current workspace protocol exposes reset/step public observations. report.md and analysis.json have separate versions and are updated with an idempotency key. A 409 requires refreshed evidence or artifact state; a 504 leaves the write outcome unknown. Public validation checks consistency and freshness. Terminal grading independently recomputes the assigned bounded result and verifies evidence timing, protected content, final reads, current validation and duplicate effects. A legitimate missing-evidence response preserves the initial files and ends blocked.

Model input contains only the initial public observation, preceding public actions and observations, and remaining budgets. Scenarios, future source changes, original provenance snapshots, reference trajectories and terminal grader state stay evaluator-side. Visible decision summaries are retained; private reasoning is omitted. Raw snapshots belong to evaluation and replay, while exported RL transitions contain only public observations, actions, rewards and terminal flags.

Source permission and split are separate constraints. Archived report derivatives retain diagnostic-only development use. Only eligible authored synthetic train families may enter positive SFT or RL training exports. Failed eligible train trajectories can supply RL transitions, but are never labeled successful demonstrations. Model identity is the requested configuration; no provider-signed model attestation is claimed.

The following sections preserve the original v0.2 interface and historical boundaries; they do not override a later version's explicit task configuration.

---

# Local protocol, quality gates, and limitations

Version 0.2 adds finite production batches and the Codex CLI adapter. The original trusted-command interface below remains available for controls. See [running batches](RUN.zh-CN.md) for executable commands and current live results.

## Observed model adapter

The batch configuration selects policy codex, an explicit requested model, output-use policy, and finite call/time budgets. Each task step starts one non-interactive CLI invocation and records the host request, emitted visible events, session identity, returned usage, status, and a capture digest. Reasoning events are omitted. Authentication remains in the CLI login store.

The CLI is invoked with a read-only sandbox, shell/web/app/plugin/delegation features disabled for the invocation, and an empty task working directory. Any unexpected runtime tool item causes the capture to fail validation. This is a controlled model-policy interface; the host's simulated fetch_source tool performs the actual environment transition.

actor_kind=model_cli identifies an observed client invocation. model_requested is configuration; model_reported stays null when the client does not provide it. The capture is not provider-signed attestation, and request.json is not the client's full internal system context. Failed calls and unknown usage remain distinguishable from completed calls.

The export gate rechecks request inputs against the task and preceding observations, client events against the returned action and usage, and capture references against the host event chain. It also checks model-output rights in addition to task rights. The supplied policy allows internal diagnostics only.

## Batch admission and recovery

pipeline freezes its configuration, generates task families, assigns run IDs, executes jobs, and creates diagnostic/SFT packages scoped to those run IDs. Budget reservations are durably saved before each adapter invocation; unknown calls are not refunded. Completed jobs are skipped on restart. An interrupted running job without a valid completed record becomes interrupted, with its partial files retained. It is not automatically reissued.

An OS file lock prevents concurrent workers for the same batch and is released on worker exit. The original batch deadline and admission count persist across restarts. The count limits adapter invocations, not internal CLI transport retries; this adapter does not enforce a dollar budget.

Model call inputs, captures, and visible events are embedded in accepted diagnostic exports. Complete resettable evaluation environments and recurring service installation remain outside this version.

## Data objects

A task stores a public goal, available source identifiers, a synthetic environment, an evaluator-side deterministic oracle, rights metadata, and a family identifier. A run stores the observed visible loop plus a task snapshot. The oracle and environment are excluded from external command input.

The independent provenance dimensions are:

- Task origin: this generator uses `synthetic`; imported existing work uses `observed_workflow`.
- Execution: generated control runs use `closed_world_observed`; imported summaries use `imported_metadata`.
- Actor: `scripted_policy`, `external_command`, `model_cli`, or `recorded_model_review`.

Here `closed_world_observed` means execution against the simulated task environment. It does not mean an operating-system security sandbox. An external command remains a trusted program that can access its own host permissions.

## Trusted command adapter

`--policy command --command-config path.json` reads a JSON file with a static nonempty `argv` array. The runner invokes it without a shell. Each action receives one JSON object on standard input:

```json
{
  "protocol": "0.1",
  "task": {
    "question": "Read the supplied source...",
    "source_ids": ["source-1"],
    "tools": ["fetch_source", "submit_answer"]
  },
  "observations": []
}
```

Return exactly one action object on standard output:

```json
{"tool": "fetch_source", "source_id": "source-1"}
```

Or submit an answer:

```json
{
  "tool": "submit_answer",
  "verdict": "answered",
  "answer": {"deployment": "available", "billing_unit": "seat", "monthly_price": 100},
  "evidence_ids": ["source-1"]
}
```

The command is restarted for each step and receives all observations so far. It is responsible for any conversation state it requires. A future provider adapter must additionally record actual model identity, request identifiers, visible messages, response status, and usage. The current adapter supplies no authenticity guarantee and is rejected by the SFT gate.

The default per-call timeout is at most five seconds or the remaining task time, whichever is smaller. A timed-out direct child is stopped by Python; cancellation of an already-issued remote request is unknown. This is a local control runner, not a production inference supervisor. The output-length check runs after capture and is not a hard memory limit. Do not execute untrusted programs through this adapter.

## Automatic decisions

1. Execute within the step/time/tool-retry limits.
2. Keep all observed errors and terminal outcomes.
3. Grade submitted facts and evidence using the task's deterministic oracle.
4. Recheck export consistency against the stored task and visible events.
5. Check purpose-specific allowed uses, trace coverage, lineage, and split.
6. Export eligible records; quarantine the rest with reason codes.

`pass` and `fail` describe the submitted answer under this narrow grader. `not_assessed` means no answer was submitted. A timeout or exhausted budget can still be a valid diagnostic trace; it never becomes a successful training demonstration.

Correct abstention requires observed terminal 404 responses for all required sources, without a successful observation of them. Correct answers require observed evidence and exact oracle facts. This is structured fact verification, not a general judge of research report quality.

Quarantine is terminal for this local run. There is no human queue. Automatic alternate-model checks and bounded repair attempts are planned, not implemented here.

## Research Toolkit import

```powershell
py -3 -B -m agentdata --root data import-workflow "path/to/selected/research-task"
```

Only `logs/review.jsonl` rows whose `record_type` is `model_review` are imported, and only selected metadata fields are retained. Original task files are not modified. No filesystem-wide discovery occurs.

Imports remain `partial_review_metadata`, with unverified rights and no outcome label. The quality gate quarantines them. A report's final status does not establish a full author trajectory. Missing calls, observations, and costs are not reconstructed.

## Storage and release boundaries

- Task snapshots and generated task files are immutable through this program. Runs receive unique IDs.
- Event hashes and parent chains detect inconsistencies; they do not authenticate a malicious writer who can change every file.
- Per-family deterministic hashing keeps these generated variants together. Grouping unrelated identifiers that share a real source or near-duplicate task requires a future lineage resolver.
- The diagnostic export contains visible trajectories, not a complete resettable environment or evaluation harness.
- Only selected common credential patterns are redacted. This is not comprehensive PII detection or legal rights verification.
- Unknown provider usage remains unknown, not zero.
- Raw data, export packages, and environment files containing secrets stay out of Git.
- Third-party material needs an explicit, applicable allowed-use policy before commercial packaging. A metadata flag does not create rights.

## Research evidence and operational interfaces

The research-evidence-v1 profile adds a visible source-selection contract: region and cutoff-date filters, authority then recency ordering, abstention for missing/conflicting top-ranked facts, exact winning-source citations, and annual price conversion rounded half-up. Environments use immutable response schedules. The generator source stays outside the exported customer task archives; the deterministic client protocol is distributed under the proprietary evaluation license.

Native visible-session-v1 imports retain top-level visible messages and tool interactions. Observed sessions, artifact-derived tasks, synthetic tasks, model_cli runs, external_command runs and scripted controls remain distinct provenance classes. Imported sessions without frozen environments remain unassessed and training-ineligible.

Training outputs use atd-visible-messages-v1 and atd-trajectory-preference-v1. These are vendor-neutral containers, not direct claims of compatibility with a trainer. Only the train split is eligible; task and model-output permissions are checked. Linked fresh attempts do not establish causal repair.

The factory persists immutable input jobs and frozen pipeline configurations. Supported sources are selected structured JSON facts and explicitly registered native sessions. Exact source hash/selector duplicates cannot claim different source groups. Metadata quarantine is automatic. A failed submitted answer may produce at most three linked attempts; timeouts with unknown cancellation never trigger automatic reissue.

The loopback API uses /v1/tasks, /v1/trials and /v1/trials/{id}/actions. A start request has request_id and task_id; an action has request_id, expected_step and action. SQLite transactions reserve one local trial credit, isolate owners and cache action responses by idempotency key. Trials freeze their task/environment, admit only fetch_source and submit_answer, and finish within eight actions or 300 seconds. API actors are external clients with unverified model identity.

Withdrawals match source_group or source_sha256. Export, API access and governed release resolution check current policy. Retained evidence is not deleted and previously delivered copies cannot be recalled.

Service lifecycle is explicit local start/status/stop. OS locks detect an active process; heartbeats describe progress. Cooperative stop does not cancel in-flight model calls. These are not installed operating-system services and the HTTP server is not a public production gateway.
