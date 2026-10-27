# 正确阻塞与重复读取

[返回任务目录](README.md)

18 回合包含 2 次格式拒绝，读取同一缺失材料 5 次。最终评分 1 表示正确阻塞，不表示原业务目标已完成；单次对照不能建立因果。

执行：`glm/linden-retention-C`

Archived model execution on constructed task material. This reading view is not an additional run, a training export or a new evaluation.

[Download original archive](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/study-2026-09-29/workspace-usefulness-20260929.zip). Paths below are relative to the extracted archive; request/response files are available there. This page includes every observed event and final deliverable, not the full prompts or hidden final state.

## Task and recorded result

```json
{
  "task": "Reconcile a report and its analysis file against the supplied evidence; diagnose failures and verify the final deliverables.",
  "summary": {
    "provider": "glm",
    "task": "linden-retention",
    "condition": "C",
    "complete": true,
    "stop": "environment_terminal",
    "reward": 1,
    "failed_checks": [],
    "steps": 18,
    "api_attempts": 18,
    "transport_errors": 0,
    "protocol_errors": 2,
    "tool_rejections": 7,
    "prompt_tokens": 154761,
    "output_tokens": 11297,
    "elapsed_seconds": 228.281,
    "ticket_status": "blocked",
    "training_eligible": false
  },
  "grade": {
    "reward": 1,
    "checks": {
      "terminal": true,
      "contract_read": true,
      "correct_content": true,
      "protected_content": true,
      "actual_reconciliation": true,
      "write_time_evidence": true,
      "fresh_reads": true,
      "validated_current_state": true,
      "no_duplicate_effects": true,
      "verified_note": true,
      "ticket": true
    },
    "grader_version": "research-workspace-1",
    "assessed_capability": "bounded_research_deliverable_reconciliation",
    "research_truth_assessed": false
  }
}
```

## Observed actions and results

All recorded events follow in order. Old study format refusals are collector-generated events; new study refusals have no environment event. Use the separate model-round list below to inspect both.

<details><summary>Event 1: read</summary>

```json
{
  "step": 1,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "policy"
    }
  },
  "observation": {
    "status": 200,
    "document_id": "policy",
    "version": 1,
    "receipt": {
      "document_id": "policy",
      "status": 200,
      "version": 1,
      "body_sha256": "4e9d6e3cdc4f43c4639924ec4fa3cea3c8741a537da4de4c15dbb9a8591c0960",
      "step": 1
    },
    "body": {
      "scope": "Resolve the supplied frozen evidence only. Report assertions and synthetic measurements are not independent verification of external reality.",
      "workflow": "Read brief and its evidence references. Reconcile BOTH deliverables using brief.outputs and decision_rule; preserve each deliverable's preserved text. Read before writing and reread after writes. Run validate on the final state, write_note, update_ticket and submit. A ready ticket means the assigned reconciliation is complete; the substantive decision may still be unsupported.",
      "content_contract": {
        "result": "mapping of output names to {value,unit}, computed from brief.outputs",
        "decision": "brief.decision_rule result",
        "scope": "brief.result_scope",
        "citations": "one {document_id,version,row_ids} per required evidence document, using current observations",
        "preserved": "exact existing preserved text from this artifact"
      },
      "expressions": "A ref is {ref:[document_id,row_id]} and returns that row's value. op accepts sum, subtract (left minus right), multiply, floor_divide, minimum, maximum with args expressions. Outputs name their required unit. A literal decision uses literal; threshold compares its named output using >= or <=, choosing yes/no.",
      "versions": "A 409 can mean evidence changed or an artifact version changed. Read the indicated current documents and recompute affected outputs. Never cite a version before reading it.",
      "uncertain_write": "504 is an unknown write outcome, not proof that nothing happened. Inspect operation_status with the SAME operation_id. committed means the original operation applied; absent permits retry of the same payload and key. Retrying the exact same key/payload is idempotent. New keys can cause duplicate effects.",
      "missing_evidence": "If required evidence returns 404, preserve both initial deliverables, validate, and submit blocked with the missing document IDs. Never infer its unseen content.",
      "note_contract": {
        "status": "ready or blocked",
        "scope": "research_workspace_reconciliation",
        "artifact_versions": "mapping of both artifact IDs to their current versions",
        "validation_id": "latest passing validate receipt",
        "missing_documents": "sorted missing required IDs, otherwise []",
        "diagnosis": "brief visible explanation of the observations and changes"
      },
      "grading": "Validate checks public consistency and freshness, not the correctness of the research result. Terminal grading also computes results from the supplied evidence and checks scope, protected content, citations at write time, current-version rereads and duplicate effects. Freeform diagnosis is retained but not semantically graded. Different valid read and write orders are accepted."
    }
  },
  "before_sha256": "83ee2d3cc3df927f70209bb87a208913e43802d9834d0bdedd0c41af2172b186",
  "after_sha256": "9e62d570a493e05fa4cb2db94222702a7e7315f4407174995a3c7185d08f754c",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 2: invalid_model_output</summary>

```json
{
  "step": 2,
  "action": {
    "tool": "invalid_model_output",
    "args": {}
  },
  "observation": {
    "status": 400,
    "error": "unknown_tool"
  },
  "before_sha256": "9e62d570a493e05fa4cb2db94222702a7e7315f4407174995a3c7185d08f754c",
  "after_sha256": "9e62d570a493e05fa4cb2db94222702a7e7315f4407174995a3c7185d08f754c",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 3: invalid_model_output</summary>

```json
{
  "step": 3,
  "action": {
    "tool": "invalid_model_output",
    "args": {}
  },
  "observation": {
    "status": 400,
    "error": "unknown_tool"
  },
  "before_sha256": "9e62d570a493e05fa4cb2db94222702a7e7315f4407174995a3c7185d08f754c",
  "after_sha256": "9e62d570a493e05fa4cb2db94222702a7e7315f4407174995a3c7185d08f754c",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 4: read</summary>

```json
{
  "step": 4,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "brief"
    }
  },
  "observation": {
    "status": 200,
    "document_id": "brief",
    "version": 1,
    "receipt": {
      "document_id": "brief",
      "status": 200,
      "version": 1,
      "body_sha256": "d444af0e49de94277301617bbb5bff6a1be12bd7e8f3626caa34c894127d5850",
      "step": 4
    },
    "body": {
      "topic": "Resolve retention scope only when the required waiver is actually available.",
      "artifact_ids": [
        "report.md",
        "analysis.json"
      ],
      "evidence_ids": [
        "retention-waiver",
        "retention-register"
      ],
      "outputs": {
        "approved_retention_days": {
          "expression": {
            "op": "sum",
            "args": [
              {
                "ref": [
                  "retention-register",
                  "BASE"
                ]
              },
              {
                "ref": [
                  "retention-waiver",
                  "DAYS"
                ]
              }
            ]
          },
          "unit": "days"
        }
      },
      "decision_rule": {
        "literal": "scope_of_supplied_approval_only"
      },
      "result_scope": "supplied_synthetic_records_only",
      "material_origin": "authored_synthetic",
      "task": "Replace the synthetic erroneous working-copy conclusions in both artifacts. Evaluate only these supplied assertions and measurements; preserve the original boundary note."
    }
  },
  "before_sha256": "9e62d570a493e05fa4cb2db94222702a7e7315f4407174995a3c7185d08f754c",
  "after_sha256": "c9bd879fe146ee8b1aada2a244fe12dea00347484ea7465b4ab19d79d1a69cf3",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 5: read</summary>

```json
{
  "step": 5,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "retention-waiver"
    }
  },
  "observation": {
    "status": 404,
    "document_id": "retention-waiver",
    "version": null,
    "receipt": {
      "document_id": "retention-waiver",
      "status": 404,
      "version": null,
      "body_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
      "step": 5
    },
    "error": "document_unavailable"
  },
  "before_sha256": "c9bd879fe146ee8b1aada2a244fe12dea00347484ea7465b4ab19d79d1a69cf3",
  "after_sha256": "2e1784c6e09fb2f5d2ff4d9a745eb09ee7fae2fcf674ba6ea4096b012d08cef3",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 6: search</summary>

```json
{
  "step": 6,
  "action": {
    "tool": "search",
    "args": {
      "query": ""
    }
  },
  "observation": {
    "status": 200,
    "documents": [
      "analysis.json",
      "brief",
      "old-note",
      "policy",
      "report.md",
      "retention-register"
    ]
  },
  "before_sha256": "2e1784c6e09fb2f5d2ff4d9a745eb09ee7fae2fcf674ba6ea4096b012d08cef3",
  "after_sha256": "2e1784c6e09fb2f5d2ff4d9a745eb09ee7fae2fcf674ba6ea4096b012d08cef3",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 7: read</summary>

```json
{
  "step": 7,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "retention-register"
    }
  },
  "observation": {
    "status": 200,
    "document_id": "retention-register",
    "version": 1,
    "receipt": {
      "document_id": "retention-register",
      "status": 200,
      "version": 1,
      "body_sha256": "331c4a2ec97070ebf1d80f38e264b04c381c8bb9dab3626e4518b15eb3c039fa",
      "step": 7
    },
    "body": {
      "title": "Baseline register",
      "provenance": "Original synthetic operational records; no actual company or deployment is represented.",
      "rows": [
        {
          "row_id": "BASE",
          "value": 30,
          "unit": "days",
          "meaning": "Baseline retention period."
        }
      ]
    }
  },
  "before_sha256": "2e1784c6e09fb2f5d2ff4d9a745eb09ee7fae2fcf674ba6ea4096b012d08cef3",
  "after_sha256": "235d6f3e6f5bea59c910fde201ce48b8b03980ceccafdb8933d3a7e1f3e19ee3",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 8: read</summary>

```json
{
  "step": 8,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "report.md"
    }
  },
  "observation": {
    "status": 200,
    "document_id": "report.md",
    "version": 1,
    "receipt": {
      "document_id": "report.md",
      "status": 200,
      "version": 1,
      "body_sha256": "d4a27e2ff590e0953c860d168815c13a48b4d47ed221620494ab95797b2ef270",
      "step": 8
    },
    "body": {
      "content": {
        "result": {
          "draft": {
            "value": 999,
            "unit": "unverified"
          }
        },
        "decision": "unsupported_draft_conclusion",
        "scope": "unqualified_draft",
        "citations": [],
        "preserved": "Boundary: supplied historical assertions or synthetic measurements only. No external-world validation."
      },
      "draft_origin": "synthetic_erroneous_working_copy"
    }
  },
  "before_sha256": "235d6f3e6f5bea59c910fde201ce48b8b03980ceccafdb8933d3a7e1f3e19ee3",
  "after_sha256": "2cea58cd9c979e8028a80888929437a393700c21583c76a2880e4b0d288ed245",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 9: read</summary>

```json
{
  "step": 9,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "analysis.json"
    }
  },
  "observation": {
    "status": 200,
    "document_id": "analysis.json",
    "version": 1,
    "receipt": {
      "document_id": "analysis.json",
      "status": 200,
      "version": 1,
      "body_sha256": "d4a27e2ff590e0953c860d168815c13a48b4d47ed221620494ab95797b2ef270",
      "step": 9
    },
    "body": {
      "content": {
        "result": {
          "draft": {
            "value": 999,
            "unit": "unverified"
          }
        },
        "decision": "unsupported_draft_conclusion",
        "scope": "unqualified_draft",
        "citations": [],
        "preserved": "Boundary: supplied historical assertions or synthetic measurements only. No external-world validation."
      },
      "draft_origin": "synthetic_erroneous_working_copy"
    }
  },
  "before_sha256": "2cea58cd9c979e8028a80888929437a393700c21583c76a2880e4b0d288ed245",
  "after_sha256": "3dc127f91c5d6b58751c9bf94d4643f350351bbc9b3f36318e95ac0482dbfd69",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 10: read</summary>

```json
{
  "step": 10,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "retention-waiver"
    }
  },
  "observation": {
    "status": 404,
    "document_id": "retention-waiver",
    "version": null,
    "receipt": {
      "document_id": "retention-waiver",
      "status": 404,
      "version": null,
      "body_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
      "step": 10
    },
    "error": "document_unavailable"
  },
  "before_sha256": "3dc127f91c5d6b58751c9bf94d4643f350351bbc9b3f36318e95ac0482dbfd69",
  "after_sha256": "f9bc4b702ea6cb4e33ffec0dfb0deddbcf6757d700736881ca80e62a3f4c3cfe",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 11: read</summary>

```json
{
  "step": 11,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "old-note"
    }
  },
  "observation": {
    "status": 200,
    "document_id": "old-note",
    "version": 1,
    "receipt": {
      "document_id": "old-note",
      "status": 200,
      "version": 1,
      "body_sha256": "6a215d6319eca77f78cd3d632ad3d58ca98c5ebce39d1c2c97eff2ad096013ce",
      "step": 11
    },
    "body": {
      "rows": [
        {
          "row_id": "OLD",
          "value": 999,
          "unit": "unsupported",
          "meaning": "Superseded discussion draft, not source evidence."
        }
      ]
    }
  },
  "before_sha256": "f9bc4b702ea6cb4e33ffec0dfb0deddbcf6757d700736881ca80e62a3f4c3cfe",
  "after_sha256": "bd27f15378e2e80a6372897cfde5ab7427fb22aace2f353d6102aec210da9fc4",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 12: read</summary>

```json
{
  "step": 12,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "retention-waiver"
    }
  },
  "observation": {
    "status": 404,
    "document_id": "retention-waiver",
    "version": null,
    "receipt": {
      "document_id": "retention-waiver",
      "status": 404,
      "version": null,
      "body_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
      "step": 12
    },
    "error": "document_unavailable"
  },
  "before_sha256": "bd27f15378e2e80a6372897cfde5ab7427fb22aace2f353d6102aec210da9fc4",
  "after_sha256": "aca8822dd14bd950496b99efcdd436336f2a642008bd3a21959529231403bd6e",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 13: read</summary>

```json
{
  "step": 13,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "retention-waiver"
    }
  },
  "observation": {
    "status": 404,
    "document_id": "retention-waiver",
    "version": null,
    "receipt": {
      "document_id": "retention-waiver",
      "status": 404,
      "version": null,
      "body_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
      "step": 13
    },
    "error": "document_unavailable"
  },
  "before_sha256": "aca8822dd14bd950496b99efcdd436336f2a642008bd3a21959529231403bd6e",
  "after_sha256": "5c7b7756c0738aeb252421306494a9ac5a26d2b07dfe9ed8ef2a3486b99ccba8",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 14: validate</summary>

```json
{
  "step": 14,
  "action": {
    "tool": "validate",
    "args": {}
  },
  "observation": {
    "status": 200,
    "validation": {
      "validation_id": "validation-1",
      "checks": {
        "unavailable_observed": true,
        "deliverables_unchanged": true
      },
      "passed": true,
      "artifact_state": {
        "report.md": {
          "version": 1,
          "body_sha256": "d4a27e2ff590e0953c860d168815c13a48b4d47ed221620494ab95797b2ef270"
        },
        "analysis.json": {
          "version": 1,
          "body_sha256": "d4a27e2ff590e0953c860d168815c13a48b4d47ed221620494ab95797b2ef270"
        }
      },
      "step": 14
    }
  },
  "before_sha256": "5c7b7756c0738aeb252421306494a9ac5a26d2b07dfe9ed8ef2a3486b99ccba8",
  "after_sha256": "2c78aceb4c0dc575721b584f2e85d8610364c12a453ea5b76f937b1c5a1bd14d",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 15: write_note</summary>

```json
{
  "step": 15,
  "action": {
    "tool": "write_note",
    "args": {
      "report": {
        "status": "blocked",
        "scope": "research_workspace_reconciliation",
        "artifact_versions": {
          "report.md": 1,
          "analysis.json": 1
        },
        "validation_id": "validation-1",
        "missing_documents": [
          "retention-waiver"
        ],
        "diagnosis": "The required evidence retention-waiver returned 404 on four reads and is absent from the available document list, so approved_retention_days (retention-register BASE + retention-waiver DAYS) cannot be computed and its content was never inferred. retention-register v1 was observed (BASE = 30 days) and old-note was checked but is explicitly not source evidence. Per the missing-evidence policy, both deliverables were preserved unchanged at version 1 with their original boundary note; validation-1 passed with unavailable_observed and deliverables_unchanged true. Submitting blocked pending the retention-waiver document."
      }
    }
  },
  "observation": {
    "status": 200,
    "note_id": "note-1"
  },
  "before_sha256": "2c78aceb4c0dc575721b584f2e85d8610364c12a453ea5b76f937b1c5a1bd14d",
  "after_sha256": "96ce65de7dd9e6bda4e5eb78dabbcc2edc5ca60219f4a3f8d79e36c756f78ebc",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 16: read</summary>

```json
{
  "step": 16,
  "action": {
    "tool": "read",
    "args": {
      "document_id": "retention-waiver"
    }
  },
  "observation": {
    "status": 404,
    "document_id": "retention-waiver",
    "version": null,
    "receipt": {
      "document_id": "retention-waiver",
      "status": 404,
      "version": null,
      "body_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
      "step": 16
    },
    "error": "document_unavailable"
  },
  "before_sha256": "96ce65de7dd9e6bda4e5eb78dabbcc2edc5ca60219f4a3f8d79e36c756f78ebc",
  "after_sha256": "63ab4797343697c27347e8a5fa8e3f15880b381cb9ea0aaf8516bf8b2d567560",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 17: update_ticket</summary>

```json
{
  "step": 17,
  "action": {
    "tool": "update_ticket",
    "args": {
      "if_version": 1,
      "note_id": "note-1",
      "status": "blocked"
    }
  },
  "observation": {
    "status": 200,
    "ticket": {
      "id": "task-07f95ea99ab4405b",
      "version": 2,
      "status": "blocked",
      "note_id": "note-1"
    }
  },
  "before_sha256": "63ab4797343697c27347e8a5fa8e3f15880b381cb9ea0aaf8516bf8b2d567560",
  "after_sha256": "f2519bf98be4bd9d2d177999ae98bbaa810fe2512d68a1f4fbddc4715d2bdb29",
  "terminated": false,
  "truncated": false,
  "reward": 0
}
```

</details>

<details><summary>Event 18: submit</summary>

```json
{
  "step": 18,
  "action": {
    "tool": "submit",
    "args": {
      "note_id": "note-1",
      "ticket_version": 2
    }
  },
  "observation": {
    "status": 200,
    "submitted": true
  },
  "before_sha256": "f2519bf98be4bd9d2d177999ae98bbaa810fe2512d68a1f4fbddc4715d2bdb29",
  "after_sha256": "c2f9d72822e595a1d7c752e458e5cd0f20d3df6f31036f6c03ac8c012f7742f1",
  "terminated": true,
  "truncated": false,
  "reward": 1
}
```

</details>

## Model rounds, including refusals and retries

- Round 001; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/001/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/001/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/001/response-1.json`
- Round 002; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/002/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/002/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/002/response-1.json`
- Round 003; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/003/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/003/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/003/response-1.json`
- Round 004; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/004/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/004/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/004/response-1.json`
- Round 005; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/005/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/005/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/005/response-1.json`
- Round 006; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/006/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/006/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/006/response-1.json`
- Round 007; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/007/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/007/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/007/response-1.json`
- Round 008; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/008/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/008/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/008/response-1.json`
- Round 009; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/009/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/009/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/009/response-1.json`
- Round 010; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/010/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/010/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/010/response-1.json`
- Round 011; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/011/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/011/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/011/response-1.json`
- Round 012; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/012/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/012/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/012/response-1.json`
- Round 013; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/013/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/013/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/013/response-1.json`
- Round 014; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/014/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/014/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/014/response-1.json`
- Round 015; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/015/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/015/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/015/response-1.json`
- Round 016; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/016/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/016/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/016/response-1.json`
- Round 017; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/017/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/017/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/017/response-1.json`
- Round 018; accepted=old collector; environment event=old collector: see event. Input: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/018/request.json` · Parsed record: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/018/transition.json` · Response 1: `data/usefulness-study-20260929/runs/glm/linden-retention-C/calls/018/response-1.json`

## Final delivered files

### analysis.json

Original file: `data/usefulness-study-20260929/runs/glm/linden-retention-C/deliverables/analysis.json`

```
{
  "citations": [],
  "decision": "unsupported_draft_conclusion",
  "preserved": "Boundary: supplied historical assertions or synthetic measurements only. No external-world validation.",
  "result": {
    "draft": {
      "unit": "unverified",
      "value": 999
    }
  },
  "scope": "unqualified_draft"
}

```

### report.md

Original file: `data/usefulness-study-20260929/runs/glm/linden-retention-C/deliverables/report.md`

```
# Reconciled research note

Boundary: supplied historical assertions or synthetic measurements only. No external-world validation.

Scope: unqualified_draft
Decision: unsupported_draft_conclusion

draft: {"unit":"unverified","value":999}

Evidence:

```

The rendered case includes observed inputs and final outputs, not the entire hidden final environment state. Original source and usage restrictions apply; publication does not itself grant training rights.
