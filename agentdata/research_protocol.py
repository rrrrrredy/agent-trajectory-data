"""Deterministic evidence-selection protocol; usable by the proprietary eval client."""
from __future__ import annotations
import math
from decimal import Decimal, ROUND_HALF_UP

PROFILE = "research-evidence-v1"
FIELDS = {"deployment": "string", "billing_unit": "string", "monthly_price": "number"}
AUTHORITY = {"community": 0, "vendor": 1, "official": 2}


def equal_json(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(left) and math.isfinite(right) and Decimal(str(left)) == Decimal(str(right))
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(equal_json(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equal_json(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def resolve(public, documents):
    rule = public["selection"]
    candidates = []
    for doc in documents:
        if (doc["region"] != rule["region"] or doc["published_at"] > rule["as_of"]
                or AUTHORITY.get(doc["authority"], -1) < rule["minimum_authority"]):
            continue
        candidates.append(doc)
    if not candidates:
        return {"verdict": "insufficient_evidence", "answer": {}, "evidence_ids": []}
    # The question explicitly defines authority/date ordering and tie behavior.
    rank = max((AUTHORITY[d["authority"]], d["published_at"]) for d in candidates)
    winners = [d for d in candidates if (AUTHORITY[d["authority"]], d["published_at"]) == rank]
    facts = [d.get("facts", {}) for d in winners]
    if any(not all(k in f for k in ("deployment", "billing_unit", "price", "period"))
           for f in facts) or any(not equal_json(facts[0], f) for f in facts[1:]):
        return {"verdict": "insufficient_evidence", "answer": {}, "evidence_ids": []}
    fact = facts[0]
    if (fact["period"] not in {"month", "year"} or fact["billing_unit"] not in {"seat", "workspace"}
            or fact["deployment"] not in {"available", "planned"}
            or isinstance(fact["price"], bool) or not isinstance(fact["price"], (int, float))
            or not math.isfinite(fact["price"]) or fact["price"] < 0):
        return {"verdict": "insufficient_evidence", "answer": {}, "evidence_ids": []}
    price = Decimal(str(fact["price"]))
    if fact["period"] == "year":
        price /= Decimal(12)
    # monthly_price means one billing unit, not total cost for an invented user count.
    price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"verdict": "answered",
            "answer": {"deployment": fact["deployment"], "billing_unit": fact["billing_unit"],
                       "monthly_price": float(price)},
            "evidence_ids": sorted(d["source_id"] for d in winners)}


def reference_action(public, observations):
    for source in public["source_ids"]:
        states = [o["status"] for o in observations if o["source_id"] == source]
        if not states or states[-1] == 429:
            return {"tool": "fetch_source", "source_id": source}
    documents = [o["document"] for o in observations if o["status"] == 200]
    result = resolve(public, documents)
    return {"tool": "submit_answer", **result}


def grade(task, submission, observations):
    label = {"source": "deterministic", "version": PROFILE, "outcome": "not_assessed",
             "passed": None, "failure_codes": ["no_submission"]}
    if submission is None:
        return label
    errors = []
    if not isinstance(submission, dict):
        return {**label, "outcome": "fail", "passed": False, "failure_codes": ["invalid_submission"]}
    required = task["public"]["source_ids"]
    for source in required:
        statuses = [o["status"] for o in observations if o.get("source_id") == source]
        if not statuses or statuses[-1] not in {200, 404}:
            errors.append("sources_not_checked")
    expected = task["oracle"]
    if submission.get("verdict") != expected["verdict"]:
        errors.append("wrong_evidence_decision")
    if not equal_json(submission.get("answer"), expected["answer"]):
        errors.append("incorrect_answer")
    evidence = submission.get("evidence_ids")
    if not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence):
        errors.append("invalid_evidence_ids")
        evidence = []
    observed = {o["source_id"] for o in observations if o.get("status") == 200}
    if set(evidence) - observed:
        errors.append("unobserved_evidence")
    if set(evidence) != set(expected["evidence_ids"]):
        errors.append("wrong_source_selection")
    return {**label, "outcome": "fail" if errors else "pass", "passed": not errors,
            "failure_codes": sorted(set(errors))}
