# Local protocol, quality gates, and limitations

## Data objects

A task stores a public goal, available source identifiers, a synthetic environment, a private deterministic oracle, rights metadata, and a family identifier. A run stores the observed visible loop plus a task snapshot. The oracle and environment are excluded from external command input.

The three independent provenance dimensions are:

- Task origin: this generator uses `synthetic`; imported existing work uses `observed_workflow`.
- Execution: generated control runs use `closed_world_observed`; imported summaries use `imported_metadata`.
- Actor: `scripted_policy`, `external_command`, or `recorded_model_review`.

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
