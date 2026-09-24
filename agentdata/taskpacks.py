"""Deterministic intake of selected machine-readable facts, with explicit lineage."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path
from .core import SCHEMA, digest, read, split_for, write_new, redact

SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")
USES = {"diagnostic", "sft", "preference", "evaluation_distribution"}


def scalar(value):
    return value is None or isinstance(value, (str, bool, int)) or (
        isinstance(value, float) and __import__("math").isfinite(value))



def field_types(facts):
    return {key: ("null" if val is None else "boolean" if isinstance(val, bool)
                 else "integer" if isinstance(val, int) else "number"
                 if isinstance(val, float) else "string") for key, val in facts.items()}


def valid_receipt(receipt):
    return isinstance(receipt, dict) and all(
        isinstance(receipt.get(k), str) and receipt[k]
        for k in ("task_id", "occurred_at", "workflow_id"))

def validate_task(task):
    """This adapter supports one frozen structured source, not arbitrary research."""
    if not isinstance(task, dict):
        raise ValueError("task_not_object")
    if task.get("profile") == "research-evidence-v1":
        from .research_tasks import validate_research_task
        return validate_research_task(task)
    for key in ("task_id", "family_id"):
        if not isinstance(task.get(key), str) or not SAFE_ID.fullmatch(task[key]):
            raise ValueError("invalid_task_identity")
    if task.get("split") != split_for(task["family_id"]):
        raise ValueError("family_split_mismatch")
    if task.get("task_origin") not in {"synthetic", "artifact_derived", "observed_task"}:
        raise ValueError("unsupported_task_origin")
    rights = task.get("rights", {})
    if (not isinstance(rights, dict) or not rights.get("basis")
            or not isinstance(rights.get("allowed_uses"), list)
            or any(x not in USES for x in rights["allowed_uses"])):
        raise ValueError("invalid_rights_policy")
    public, env, oracle = task["public"], task["environment"], task["oracle"]
    if (not isinstance(public, dict) or not isinstance(env, dict) or len(env) != 1
            or public.get("source_ids") != list(env)
            or public.get("tools") != ["fetch_source", "submit_answer"]):
        raise ValueError("unsupported_environment")
    config = next(iter(env.values()))
    facts = config["document"]["facts"]
    if (not isinstance(facts, dict) or not facts
            or not all(isinstance(k, str) and k and scalar(v) for k, v in facts.items())
            or config.get("responses") not in ([200], [404], [429, 200])):
        raise ValueError("unsupported_facts_or_responses")
    expected = ({"verdict": "insufficient_evidence", "answer": {}}
                if config["responses"] == [404] else {"verdict": "answered", "answer": facts})
    types = field_types(facts)
    default_types = {"deployment": "string", "billing_unit": "string", "monthly_price": "integer"}
    if public.get("answer_fields", default_types) != types:
        raise ValueError("answer_schema_inconsistent_with_facts")
    if task.get("grading_contract", "closed-facts-v1") not in {"closed-facts-v1", "closed-facts-v2"}:
        raise ValueError("unsupported_grading_contract")
    if task["task_origin"] != "synthetic":
        lineage = task.get("lineage")
        if not isinstance(lineage, dict) or not isinstance(lineage.get("source_group"), str):
            raise ValueError("missing_source_lineage")
        if (not re.fullmatch(r"[a-f0-9]{64}", str(lineage.get("source_sha256", "")))
                or lineage["source_group"] != task.get("source_group")
                or task["family_id"] != "facts-" + digest(lineage["source_group"])[:24]):
            raise ValueError("inconsistent_source_lineage")
        if task.get("grading_contract") != "closed-facts-v2":
            raise ValueError("structured_facts_require_typed_grader")
        receipt = lineage.get("task_receipt")
        basis = lineage.get("origin_basis")
        if task["task_origin"] == "observed_task":
            if not valid_receipt(receipt) or basis != "caller_workflow_receipt":
                raise ValueError("observed_task_requires_workflow_receipt")
        elif receipt is not None or basis != "selected_existing_artifact":
            raise ValueError("artifact_origin_mismatch")
    if digest(oracle) != digest(expected):
        raise ValueError("oracle_inconsistent_with_environment")
    if task != redact(task):
        raise ValueError("credential_pattern_detected")
    return task


def capture_facts(root, source, selectors, source_group, rights, origin="artifact_derived",
                  task_receipt=None):
    """Capture JSON pointers supplied by a workflow, without LLM-generated labels."""
    if not isinstance(source_group, str) or not source_group.strip():
        raise ValueError("source_group_required")
    if origin not in {"artifact_derived", "observed_task"}:
        raise ValueError("unsupported_origin")
    if origin == "observed_task" and not valid_receipt(task_receipt):
        raise ValueError("observed_task_requires_workflow_receipt")
    source = Path(source)
    if source.stat().st_size > 2_000_000:
        raise ValueError("source_too_large")
    raw = source.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(selectors, dict) or not 1 <= len(selectors) <= 32:
        raise ValueError("selectors_must_be_nonempty_mapping")
    facts = {}
    for name, pointer in selectors.items():
        if not isinstance(name, str) or not SAFE_ID.fullmatch(name):
            raise ValueError("invalid_field_name")
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("selector_must_be_json_pointer")
        selected = value
        for part in pointer[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            selected = selected[int(part)] if isinstance(selected, list) else selected[part]
        if not scalar(selected) or (isinstance(selected, str) and len(selected) > 2000):
            raise ValueError("selected_fact_must_be_bounded_scalar")
        facts[name] = selected
    family = "facts-" + digest(source_group)[:24]
    fingerprint = hashlib.sha256(raw).hexdigest()
    source_id = family + "-source"
    public = {
        "question": "Read the supplied structured source and return exactly these facts: "
                    + ", ".join(facts) + ". Cite successfully observed source ids. "
                    "If the required source is unavailable, return insufficient_evidence "
                    "with an empty answer. A 429 is transient and may be retried.",
        "source_ids": [source_id], "tools": ["fetch_source", "submit_answer"],
        "answer_fields": field_types(facts),
    }
    lineage = {"source_sha256": fingerprint, "source_group": source_group,
               "selectors": selectors, "origin_basis": "caller_workflow_receipt"
               if origin == "observed_task" else "selected_existing_artifact",
               "task_receipt": task_receipt}
    tasks = []
    for variant, statuses in (("normal", [200]), ("missing_source", [404]),
                              ("transient_error", [429, 200])):
        task_id = family + "-" + digest([fingerprint, selectors, rights, origin, task_receipt, "closed-facts-v2"])[:16] + "-" + variant
        task = {
            "schema_version": SCHEMA, "task_id": task_id, "family_id": family,
            "split": split_for(family), "task_origin": origin, "source_group": source_group,
            "variant": variant, "generator": {"adapter": "structured-artifact-v1"},
            "grading_contract": "closed-facts-v2",
            "rights": copy.deepcopy(rights), "lineage": lineage, "public": public,
            "environment": {source_id: {"document": {
                "source_id": source_id, "title": "Frozen selected machine-readable facts",
                "facts": facts}, "responses": statuses}},
            "oracle": {"verdict": "insufficient_evidence" if statuses == [404] else "answered",
                       "answer": {} if statuses == [404] else facts},
        }
        validate_task(task)
        tasks.append(task)
    # Validate the entire intake before any task is committed.
    paths = [Path(root) / "tasks" / (task["task_id"] + ".json") for task in tasks]
    for path, task in zip(paths, tasks):
        if path.exists() and read(path) != task:
            raise ValueError("immutable_intake_conflict")
    for path, task in zip(paths, tasks):
        write_new(path, task)
    receipt = {"profile": "structured-artifact-v1", "task_ids": [t["task_id"] for t in tasks],
               "family_id": family, "split": split_for(family), "task_origin": origin,
               "lineage": lineage, "oracle_basis": "deterministic_selected_source_facts",
               "scope": "Fact extraction and tool recovery; not overall research quality."}
    write_new(Path(root) / "intakes" / (digest(receipt) + ".json"), receipt)
    return receipt
