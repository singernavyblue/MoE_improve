#!/usr/bin/env python3
"""Shared verification followed by always-on repair generation and pooling."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from run_proco_keyverify import PARTICIPANTS, _call, _json_call, _parse_json_loose, _save_json


def _answer_letter(value: Any) -> str | None:
    if value is None:
        return None
    matches = re.findall(r"\b([A-D])\b", str(value).upper())
    return matches[-1] if matches else None


def _raw_answer_letter(raw: str) -> str | None:
    patterns = (
        r"\[FINAL_ANSWER\]\s*[:=]?\s*\(?([A-D])\)?",
        r"(?:correct|final)\s+answer\s*(?:is|:|=)\s*\(?([A-D])\)?",
        r"\"answer\"\s*:\s*\"?([A-D])\"?",
    )
    for pattern in patterns:
        match = re.search(pattern, raw or "", re.I)
        if match:
            return match.group(1).upper()
    return _answer_letter(raw)


def _model_structured_call(model: str, prompt: str, max_tokens: int, required: tuple[str, ...]) -> tuple[str, dict[str, Any], str | None]:
    best_raw = ""
    best_parsed: dict[str, Any] = {}
    for retry in range(2):
        raw = _call(model, prompt, max_tokens, temperature=0.2, seed=900 + retry)
        parsed = _parse_json_loose(raw) or {}
        if len(raw) > len(best_raw):
            best_raw, best_parsed = raw, parsed
        if all(str(parsed.get(key, "")).strip() for key in required):
            return raw, parsed, _answer_letter(parsed.get("answer")) or _raw_answer_letter(raw)
        letter = _answer_letter(parsed.get("answer")) or _raw_answer_letter(raw)
        if letter:
            return raw, parsed, letter
    return best_raw, best_parsed, _answer_letter(best_parsed.get("answer")) or _raw_answer_letter(best_raw)


def _load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def _consensus_status(record: dict[str, Any], slot: int) -> str:
    entries = record.get("shared_proco", {}).get(str(slot), {})
    verdicts = [item.get("verdict") for item in entries.values()]
    if len(verdicts) == 2 and all(v == "NO_MATCH" for v in verdicts):
        return "CONFIRMED_NO_MATCH"
    if len(verdicts) == 2 and all(v == "MATCH" for v in verdicts):
        return "CONFIRMED_MATCH"
    if verdicts:
        return "MIXED_OR_INSUFFICIENT"
    return "NO_EVIDENCE"


def _chain_bundle(record: dict[str, Any]) -> str:
    blocks = []
    for slot, model in enumerate(record.get("sampled_nodes", [])):
        answer = record.get("initial_answers", {}).get(str(slot), "N/A")
        chain = record.get("initial_responses", {}).get(str(slot), "")[:1700]
        blocks.append(f"M{slot} ({model}) answer={answer}\n{chain}")
    return "\n\n".join(blocks)


def _evidence_bundle(record: dict[str, Any]) -> str:
    condition = record.get("shared_condition", {})
    lines = [f"Shared masked condition: {condition.get('text', 'missing')} ({condition.get('type', 'missing')})"]
    for slot, model in enumerate(record.get("sampled_nodes", [])):
        status = _consensus_status(record, slot)
        entries = record.get("shared_proco", {}).get(str(slot), {})
        if not entries:
            lines.append(f"M{slot} ({model}) consensus={status}")
            continue
        details = "; ".join(
            f"{verifier}: {item.get('verdict', 'UNKNOWN')} inferred={item.get('verification_answer', '')[:160]}"
            for verifier, item in entries.items()
        )
        lines.append(f"M{slot} ({model}) consensus={status}; {details}")
    return "\n".join(lines)


def _repair_prompt(record: dict[str, Any]) -> str:
    return f"""You are an independent second-round solver in a corrective multi-agent pool.
The original question is a graduate-level science multiple-choice problem.
You may keep the existing pooled answer or change it. You MUST solve the
problem again from first principles. Do not merely vote for the majority.
If all initial answers are wrong, you may produce a new option that was not in
the initial pool. Shared verification evidence is diagnostic evidence, not a
reference answer. Do not use any gold answer.

Question:
{record['question']}

Original pooled answer A_pool:
{record.get('stored_goa_answer', 'N/A')}

Frozen initial attempts:
{_chain_bundle(record)}

Shared verification evidence:
{_evidence_bundle(record)}

Return strict JSON only:
{{"answer":"A" or "B" or "C" or "D", "reason":"short recomputed justification", "key_claims":["claim 1","claim 2"]}}
Also put the answer on the first line as [FINAL_ANSWER] A.
"""


def _pool_prompt(record: dict[str, Any]) -> str:
    repairs = []
    for model in PARTICIPANTS:
        item = record.get("repair_pool", {}).get(model, {})
        repairs.append(
            f"Repair by {model}: answer={item.get('answer', 'N/A')}\n"
            f"Reason: {item.get('reason', '')}\n"
            f"Claims: {item.get('key_claims', '')}"
        )
    return f"""You are the final synthesis solver. Re-solve the question using the
original attempts, the original pooled answer, the independently generated
repairs, and the shared verification evidence. Do not select an answer only
because it is the majority. Check the key scientific condition yourself.
You may output an option that none of the initial attempts proposed.
CONFIRMED_NO_MATCH is a concrete contradiction; UNKNOWN is not evidence.
Produce one final answer and a concise derivation. Do not use any gold answer.

Question:
{record['question']}

Original pooled answer A_pool: {record.get('stored_goa_answer', 'N/A')}

Initial attempts:
{_chain_bundle(record)}

Repairs:
{chr(10).join(repairs)}

Shared verification evidence:
{_evidence_bundle(record)}

Return strict JSON only:
{{"answer":"A" or "B" or "C" or "D", "reason":"short final derivation", "decision":"KEEP_POOL" or "REPAIR" or "NEW"}}
Also put the answer on the first line as [FINAL_ANSWER] A.
"""


def _repair_answers(record: dict[str, Any]) -> list[str]:
    return [
        item.get("answer")
        for item in record.get("repair_pool", {}).values()
        if item.get("answer") in {"A", "B", "C", "D"}
    ]


def _repair_consensus(record: dict[str, Any]) -> str | None:
    for answer, count in Counter(_repair_answers(record)).items():
        if count >= 2:
            return answer
    return None


def _pool_contradicted(record: dict[str, Any]) -> bool:
    pooled = record.get("stored_goa_answer")
    for slot, answer in record.get("initial_answers", {}).items():
        if answer == pooled and _consensus_status(record, int(slot)) == "CONFIRMED_NO_MATCH":
            return True
    return False


def _accept_final(record: dict[str, Any], pooler_answer: str | None) -> tuple[str, str]:
    pooled = record.get("stored_goa_answer")
    consensus = _repair_consensus(record)
    if pooler_answer is None:
        return pooled, "fallback_A_pool_pooler_parse_failed"
    if pooler_answer == pooled:
        return pooled, "pooler_keeps_A_pool"
    if consensus and pooler_answer == consensus:
        return pooler_answer, "two_repairs_plus_pooler_agree"
    return pooled, "fallback_A_pool_insufficient_acceptance_evidence"


def _initialize(args: argparse.Namespace) -> list[dict[str, Any]]:
    if Path(args.out).exists():
        return _load_json(args.out)
    source = _load_json(args.source)
    records = []
    for raw in source[: args.limit]:
        record = dict(raw)
        record["repair_pool"] = {}
        record["pooler"] = {}
        record["final_answer"] = None
        record["final_reason"] = ""
        records.append(record)
    _save_json(args.out, records)
    return records


def run_repair(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    model = args.model
    for pos, record in enumerate(records, 1):
        existing = record.get("repair_pool", {}).get(model, {})
        if existing.get("answer") in {"A", "B", "C", "D"}:
            continue
        raw, parsed, answer = _model_structured_call(model, _repair_prompt(record), 620, ("answer", "reason"))
        record.setdefault("repair_pool", {})[model] = {
            "answer": answer,
            "reason": str(parsed.get("reason", "")),
            "key_claims": parsed.get("key_claims", []),
            "raw": raw,
        }
        _save_json(args.out, records)
        print(f"[repair {model}] {pos}/{len(records)} idx={record['idx']} answer={answer or 'PARSE_FAIL'}", flush=True)


def run_pool(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        raw, parsed, pooler_answer = _model_structured_call(args.pooler_model, _pool_prompt(record), 720, ("answer", "reason"))
        final_answer, final_reason = _accept_final(record, pooler_answer)
        record["pooler"] = {
            "model": args.pooler_model,
            "answer": pooler_answer,
            "reason": str(parsed.get("reason", "")),
            "decision": str(parsed.get("decision", "")),
            "raw": raw,
        }
        record["repair_consensus"] = _repair_consensus(record)
        record["pool_contradicted"] = _pool_contradicted(record)
        record["final_answer"] = final_answer
        record["final_reason"] = final_reason
        _save_json(args.out, records)
        print(f"[pool] {pos}/{len(records)} idx={record['idx']} pooler={pooler_answer or 'PARSE_FAIL'} final={final_answer} reason={final_reason}", flush=True)


def _mcnemar_p(fixed: int, broken: int) -> float:
    total = fixed + broken
    if not total:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(min(fixed, broken) + 1)) / (2 ** total)
    return min(1.0, 2 * tail)


def _answer(record: dict[str, Any], label: str) -> str | None:
    if label in {"stored_goa_answer", "final_answer"}:
        return record.get(label)
    if label == "pooler_answer":
        return record.get("pooler", {}).get("answer")
    return record.get(label, {}).get("answer")


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    labels = ("stored_goa_answer", "baseline_judge", "proco_judge", "baseline_swap_judge", "shared_judge", "pooler_answer", "final_answer")
    summary: dict[str, Any] = {"n": len(records), "accuracy": {}, "paired": {}, "repair": {}}
    for label in labels:
        correct = sum(_answer(record, label) == record["gold"] for record in records)
        summary["accuracy"][label] = {"correct": correct, "accuracy": correct / len(records)}
    for comparator in ("stored_goa_answer", "baseline_swap_judge", "shared_judge", "proco_judge"):
        fixed = sum(_answer(r, "final_answer") == r["gold"] and _answer(r, comparator) != r["gold"] for r in records)
        broken = sum(_answer(r, "final_answer") != r["gold"] and _answer(r, comparator) == r["gold"] for r in records)
        summary["paired"][f"final_vs_{comparator}"] = {"fixed": fixed, "broken": broken, "mcnemar_exact_p": _mcnemar_p(fixed, broken)}
    accepted = sum(r.get("final_reason", "").startswith(("two_repairs", "confirmed_pool")) for r in records)
    summary["repair"] = {
        "changed_from_A_pool": sum(_answer(r, "final_answer") != _answer(r, "stored_goa_answer") for r in records),
        "accepted_repair": accepted,
        "repair_consensus": sum(r.get("repair_consensus") is not None for r in records),
        "pool_contradicted": sum(bool(r.get("pool_contradicted")) for r in records),
        "fallback_to_A_pool": len(records) - accepted,
    }
    _save_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("repair", "pool", "summary"))
    parser.add_argument("--model", choices=PARTICIPANTS)
    parser.add_argument("--pooler-model", default="qwen", choices=PARTICIPANTS)
    parser.add_argument("--source", default="outputs/proco_keyverify_shared_10_v3.json")
    parser.add_argument("--out", default="outputs/proco_keyverify_pool_repair_10.json")
    parser.add_argument("--summary", default="outputs/proco_keyverify_pool_repair_10_summary.json")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.stage == "repair" and not args.model:
        parser.error("--model is required for repair")
    records = _initialize(args)
    if args.stage == "repair":
        run_repair(args, records)
    elif args.stage == "pool":
        run_pool(args, records)
    else:
        summarize(args, records)


if __name__ == "__main__":
    main()
