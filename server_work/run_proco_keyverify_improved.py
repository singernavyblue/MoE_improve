#!/usr/bin/env python3
"""10-item validation of a stricter ProCo-style verifier.

Differences from the earlier run:
* the condition must be quoted from the question, never selected from a chain;
* verifier generation only sees the question and proposed option, not the chain;
* each chain is verified by the other two models and only two NO_MATCH votes are
  presented as a contradiction to the judge;
* pairwise judging is order-swapped to reduce position effects.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from run_proco_keyverify import (
    JUDGE,
    PARTICIPANTS,
    _call,
    _json_call,
    _pairwise_prompt,
    _pairwise_result,
    _save_json,
)


def _load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def _normal(value: str) -> str:
    """Normalise harmless rendering differences while retaining condition content."""
    text = str(value).casefold()
    text = text.replace("−", "-").replace("–", "-").replace("×", "x")
    # Treat 10^{-9}, 10^(-9), and 10^-9 as the same quoted scientific value.
    text = re.sub(r"\^\s*\{\s*([^{}]+?)\s*\}", r"^\1", text)
    text = re.sub(r"\^\s*\(\s*([^()]+?)\s*\)", r"^\1", text)
    text = re.sub(r"\\(?:mathrm|text|rm)\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("$", "")
    return re.sub(r"\s+", " ", text).strip()


def _key_prompt(question: str, proposed_answer: str) -> str:
    return f"""Construct a strict substitute-verification task for a graduate-level
science multiple-choice question. You are auditing proposed option {proposed_answer}.
You are NOT given a reasoning chain.

Original question (including its answer choices):
{question}

Choose one objective condition that appears verbatim in the original question and
is necessary to determine whether option {proposed_answer} is correct. Quote that
exact text as key_condition. Then make a standalone verification question that
replaces exactly that condition by [X] and asks what [X] must be if option
{proposed_answer} were correct. Do not use an answer letter as the condition.

Use key_type=numeric only for a number, unit, coefficient, count, or equation
value. Otherwise use key_type=proposition for an entity, fact, or scientific
relation. The verification question must be answerable without any reasoning
chain and must not reveal the original condition outside [X].

Return strict JSON only:
{{"key_type":"numeric" or "proposition","key_condition":"exact quote from the question","verification_question":"... [X] ...","why_necessary":"one sentence"}}"""


def _solve_prompt(question: str, proposed_answer: str, verification_question: str, key_type: str) -> str:
    shape = "the normalized value and unit" if key_type == "numeric" else "a concise entity, fact, or true/false value"
    return f"""Answer a substitute-verification question independently.
You do not have access to any proposed reasoning chain. The proposed final
option is {proposed_answer}, but do not assume it is correct. Infer only what
[X] must be from the question and the verification question.

Original question:
{question}

Verification question:
{verification_question}

Return {shape}. Return strict JSON only:
{{"verification_answer":"...","reason":"one factual sentence"}}"""


def _match_prompt(key_type: str, key_condition: str, verification_question: str, predicted: str) -> str:
    rule = (
        "Compare numerical value, sign, exponent, coefficient, and essential unit."
        if key_type == "numeric" else
        "Compare the specific entity/fact/relation. A true/false label by itself is not a match unless the original condition is also exactly that truth value."
    )
    return f"""Decide a strict key-condition comparison. {rule}
Do not judge whether the option is generally plausible; judge only whether the
independently inferred [X] is equivalent to the original quoted condition.

Original condition: {key_condition}
Verification question: {verification_question}
Independently inferred [X]: {predicted}

Return strict JSON only:
{{"verdict":"MATCH" or "NO_MATCH" or "UNKNOWN","reason":"one short sentence"}}"""


def _condition_is_valid(question: str, evidence: dict[str, Any]) -> bool:
    condition = str(evidence.get("key_condition", ""))
    verify_q = str(evidence.get("verification_question", ""))
    return bool(condition and "[X]" in verify_q and _normal(condition) in _normal(question))


def _load_or_init(args: argparse.Namespace) -> list[dict[str, Any]]:
    target = Path(args.out)
    if target.exists():
        return _load_json(str(target))
    source = _load_json(args.source)
    records = []
    for raw in source[:args.limit]:
        record = dict(raw)
        record["improved_proco"] = {str(i): {} for i in range(3)}
        records.append(record)
    if len(records) != args.limit:
        raise ValueError(f"need {args.limit} frozen records, found {len(records)}")
    _save_json(args.out, records)
    return records


def run_verifier(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    verifier = args.model
    for pos, rec in enumerate(records, 1):
        for slot, origin in enumerate(rec["sampled_nodes"]):
            if origin == verifier:
                continue
            answer = rec.get("initial_answers", {}).get(str(slot))
            if answer not in {"A", "B", "C", "D"}:
                continue
            evidence = rec.setdefault("improved_proco", {}).setdefault(str(slot), {}).setdefault(verifier, {})
            if evidence.get("verdict") in {"MATCH", "NO_MATCH", "UNKNOWN"}:
                continue
            raw, parsed = _json_call(verifier, _key_prompt(rec["question"], answer), 420, ("key_type", "key_condition", "verification_question"))
            evidence.update({
                "key_raw": raw,
                "key_type": str(parsed.get("key_type", "proposition")).lower(),
                "key_condition": str(parsed.get("key_condition", "")),
                "verification_question": str(parsed.get("verification_question", "")),
                "why_necessary": str(parsed.get("why_necessary", "")),
            })
            if not _condition_is_valid(rec["question"], evidence):
                evidence.update({"verdict": "UNKNOWN", "error": "condition_not_exact_question_span"})
                _save_json(args.out, records)
                continue
            raw, parsed = _json_call(verifier, _solve_prompt(rec["question"], answer, evidence["verification_question"], evidence["key_type"]), 360, ("verification_answer",))
            evidence.update({"solve_raw": raw, "verification_answer": str(parsed.get("verification_answer", "")), "solve_reason": str(parsed.get("reason", ""))})
            if not evidence["verification_answer"]:
                evidence.update({"verdict": "UNKNOWN", "error": "verification_answer_parse_failed"})
                _save_json(args.out, records)
                continue
            raw, parsed = _json_call(verifier, _match_prompt(evidence["key_type"], evidence["key_condition"], evidence["verification_question"], evidence["verification_answer"]), 180, ("verdict",))
            verdict = str(parsed.get("verdict", "")).upper()
            evidence.update({"match_raw": raw, "verdict": verdict if verdict in {"MATCH", "NO_MATCH", "UNKNOWN"} else "UNKNOWN", "match_reason": str(parsed.get("reason", ""))})
            _save_json(args.out, records)
            print(f"[verifier {verifier}] {pos}/{len(records)} idx={rec['idx']} target=M{slot} {evidence['verdict']}", flush=True)


def _consensus(record: dict[str, Any], slot: int) -> dict[str, Any]:
    entries = record.get("improved_proco", {}).get(str(slot), {})
    verdicts = [e.get("verdict") for e in entries.values()]
    if len(verdicts) == 2 and all(v == "NO_MATCH" for v in verdicts):
        label = "CONFIRMED_NO_MATCH"
    elif len(verdicts) == 2 and all(v == "MATCH" for v in verdicts):
        label = "CONFIRMED_MATCH"
    elif verdicts:
        label = "MIXED_OR_INSUFFICIENT"
    else:
        label = "NO_EVIDENCE"
    return {"label": label, "entries": entries}


def _chain_block(record: dict[str, Any], slot: int) -> str:
    answer = record.get("initial_answers", {}).get(str(slot), "N/A")
    block = f"M{slot} proposed answer: {answer}\nOriginal chain:\n{record['initial_responses'].get(str(slot), '')[:1700]}"
    consensus = _consensus(record, slot)
    block += f"\nIndependent substitute-verification status: {consensus['label']}"
    for verifier, evidence in consensus["entries"].items():
        block += (f"\n- verifier={verifier}; key={evidence.get('key_condition', 'missing')}; "
                  f"inferred={evidence.get('verification_answer', 'missing')}; verdict={evidence.get('verdict', 'UNKNOWN')}")
    return block


def _judge_pairwise(question: str, record: dict[str, Any]) -> dict[str, Any]:
    scores = [0.0, 0.0, 0.0]
    pairs = []
    for pair_no, (a, b) in enumerate(((0, 1), (0, 2), (1, 2))):
        first = _chain_block(record, a)
        second = _chain_block(record, b)
        outcomes = []
        for reverse, left, right in ((False, first, second), (True, second, first)):
            prompt = _pairwise_prompt(question, left, right)
            prompt = prompt.replace(
                "Compare Response A and Response B strictly by factual accuracy, logical\nsoundness, and whether they answer the question. Do not prefer length or\nconfidence. No reference answer is provided.",
                "Compare Response A and Response B strictly by factual accuracy and logical soundness. Do not prefer length, model identity, or confidence. A chain is contradicted only when its status is CONFIRMED_NO_MATCH; MIXED_OR_INSUFFICIENT is not negative evidence. No reference answer is provided.",
            )
            raw, result = "", None
            for retry in range(3):
                raw = _call(JUDGE, prompt, 700, temperature=0.2, seed=700 + pair_no * 10 + retry + int(reverse) * 3)
                result = _pairwise_result(raw)
                if result is not None:
                    break
            if reverse and result in {"a", "b"}:
                result = "b" if result == "a" else "a"
            outcomes.append({"reverse": reverse, "result": result or "tie_fallback", "raw": raw})
        choices = [x["result"] for x in outcomes]
        if choices == ["a", "a"]:
            scores[a] += 1.0
            final = "a"
        elif choices == ["b", "b"]:
            scores[b] += 1.0
            final = "b"
        else:
            scores[a] += 0.5
            scores[b] += 0.5
            final = "order_disagreement_or_tie"
        pairs.append({"pair": [a, b], "result": final, "calls": outcomes})
    winner = max(range(3), key=lambda i: (scores[i], -i))
    return {"winner": winner, "answer": record["initial_answers"].get(str(winner)), "scores": scores, "pairs": pairs}


def run_judge(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, rec in enumerate(records, 1):
        if rec.get("improved_judge", {}).get("answer") in {"A", "B", "C", "D"}:
            continue
        rec["improved_judge"] = _judge_pairwise(rec["question"], rec)
        _save_json(args.out, records)
        print(f"[judge] {pos}/{len(records)} idx={rec['idx']} improved={rec['improved_judge'].get('answer')}", flush=True)


def _mcnemar_p(fixed: int, broken: int) -> float:
    n = fixed + broken
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(fixed, broken) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    def answer(rec: dict[str, Any], label: str) -> str | None:
        if label == "stored_goa_answer":
            return rec.get(label)
        return rec.get(label, {}).get("answer")
    labels = ("stored_goa_answer", "baseline_judge", "proco_judge", "improved_judge")
    summary: dict[str, Any] = {"n": len(records), "accuracy": {}, "consensus": {}}
    for label in labels:
        correct = sum(answer(rec, label) == rec["gold"] for rec in records)
        summary["accuracy"][label] = {"correct": correct, "accuracy": correct / len(records)}
    for comparator in ("baseline_judge", "proco_judge"):
        fixed = sum(answer(r, "improved_judge") == r["gold"] and answer(r, comparator) != r["gold"] for r in records)
        broken = sum(answer(r, "improved_judge") != r["gold"] and answer(r, comparator) == r["gold"] for r in records)
        summary[f"paired_improved_vs_{comparator}"] = {"fixed": fixed, "broken": broken, "mcnemar_exact_p": _mcnemar_p(fixed, broken)}
    labels_seen = [_consensus(r, i)["label"] for r in records for i in range(3)]
    summary["consensus"] = {label: labels_seen.count(label) for label in ("CONFIRMED_NO_MATCH", "CONFIRMED_MATCH", "MIXED_OR_INSUFFICIENT", "NO_EVIDENCE")}
    _save_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("verifier", "judge", "summary"))
    parser.add_argument("--model", choices=PARTICIPANTS)
    parser.add_argument("--source", default="outputs/proco_keyverify_40.json")
    parser.add_argument("--out", default="outputs/proco_keyverify_improved_10.json")
    parser.add_argument("--summary", default="outputs/proco_keyverify_improved_10_summary.json")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.stage == "verifier" and not args.model:
        parser.error("--model is required for verifier stage")
    records = _load_or_init(args)
    if args.stage == "verifier":
        run_verifier(args, records)
    elif args.stage == "judge":
        run_judge(args, records)
    else:
        summarize(args, records)


if __name__ == "__main__":
    main()
