# Agent Trajectory Data

Private, proprietary software for producing agent tasks, visible trajectories and executable evaluation suites. Routine production uses deterministic acceptance, bounded attempts, quarantine and budget stops. It has no interview, annotation or human review queue.

[当前系统与运行方式](docs/SYSTEM.zh-CN.md) · [产品结论与商业方案](docs/CONCLUSION.zh-CN.md) · [验收结果](docs/ACCEPTANCE.zh-CN.md) · [Protocol](docs/PROTOCOL.md) · [Validation](docs/VALIDATION.md)

Python 3.10+, standard library runtime. Windows/Python 3.11 was exercised.

## Produce and operate

```powershell
# Generate 30 procedural families / 300 multi-source tasks, run controls and package.
py -3 -B -m agentdata --root data/production-current factory --config configs/factory-control.json

# Watch configured sources in a hidden local background process.
py -3 -B -m agentdata --root data/production-current service-start --kind factory --config configs/factory-control.json
py -3 -B -m agentdata --root data/production-current service-status --kind factory
py -3 -B -m agentdata --root data/production-current service-stop --kind factory

# Run the tests.
py -3 -B -m unittest discover -s tests
```

Unchanged inputs are skipped. New supported source snapshots create immutable jobs. Bad inputs are quarantined without blocking other inputs. Background processes are explicitly started local processes; installation as an operating-system service or boot-time task is outside this implementation.

## Evaluate client agents

```powershell
py -3 -B -m agentdata --root data/production-current issue-key --file data/production-current/keys/demo.json --label demo --credits 20
py -3 -B -m agentdata --root data/production-current service-start --kind eval --port 8765
py -3 -B -m agentdata evaluate-api --key-file data/production-current/keys/demo.json --output artifacts/api-control.json --limit 10
py -3 -B -m agentdata --root data/production-current service-stop --kind eval
```

The API binds to 127.0.0.1. SQLite retains trial ownership, credit reservations, frozen environments and idempotent action responses across restarts. Add `--agent-config path/to/argv.json` to the client command to run your trusted local agent. The default client is an explicitly labeled scripted control. The server executes only its two declared tools and never executes client-supplied programs. Credits are local trial allowances, not payments.

The API is a local diagnostic service, not a public production deployment. Its answer key stays server-side; clients still receive public task instructions and requested tool observations. A downloaded evaluation ZIP contains readable answers and cannot serve as a hidden benchmark.

## Data and evidence

Ten procedural scenarios cover authority, dates, region, conflicting evidence, missing fields, annual price conversion, injected instructions, retries and unavailable sources. Family groups share templates; their count does not establish statistical independence or out-of-template generalization.

Structured-fact intake records source hashes and stable source groups. Native session intake retains selected visible messages and top-level tool calls/results, omits analysis/system/developer channels and labels missing environment snapshots. A partial imported session is never treated as a verified training trajectory.

Training exports include vendor-neutral messages and comparable success/failure pairs only when checks and explicit task/model-output policies permit them. Development and holdout records stay outside training; control scripts are excluded by default. The current real model output policy allows diagnostics only.

Sources can be withdrawn to block future exports, API access and governed release delivery. Previously downloaded copies cannot be recalled. Rights metadata states a policy; it does not establish legal ownership.

## Observed validation

82 tests passed. Local production created 300 scripted control runs; the standalone non-holdout suite passed 260 controls. Twelve API trials passed across process restarts. Two additional live model tasks used eight adapter calls and passed; requested model configuration and returned tokens are recorded, while billing amount and authoritative served-model version remain unknown.

Data, credentials, model captures and release archives are excluded from Git. The repository is private. There is no claim of external customer data, proven training gains, paid transactions or revenue.
