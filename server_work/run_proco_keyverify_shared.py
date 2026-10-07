#!/usr/bin/env python3
"""Shared-question, span-constrained ProCo validation on frozen GPQA chains.

The previous prototype let each verifier choose its own condition and question.
This version chooses one exact span from the question per item, masks it once,
and asks both external verifiers the same substitute question for each candidate.
Numeric spans are compared deterministically; non-numeric spans remain unknown
unless their text is reproduced exactly.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from run_proco_keyverify import JUDGE, PARTICIPANTS, _call, _json_call, _pairwise_prompt, _pairwise_result, _save_json


def _load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def _norm(text: str) -> str:
    value = str(text).casefold()
    value = value.replace("−", "-").replace("–", "-").replace("×", "x")
    value = value.replace("\\times", "x").replace("\\cdot", "*")
    value = re.sub(r"\^\s*\{\s*([^{}]+?)\s*\}", r"^\1", value)
    value = re.sub(r"\^\s*\(\s*([^()]+?)\s*\)", r"^\1", value)
    value = re.sub(r"\\(?:mathrm|text|rm)\s*\{([^{}]*)\}", r"\1", value)
    value = value.replace("$", "").replace("\\,", "")
    return re.sub(r"\s+", " ", value).strip()


def _stem_and_options(question: str) -> tuple[str, str]:
    marker = re.search(r"\n\s*(?:the\s+)?(?:answer\s+)?options?\s+(?:are|is)\s*:", question, re.I)
    if marker:
        return question[:marker.start()].strip(), question[marker.start():].strip()
    return question.strip(), ""


def _numeric_spans(stem: str) -> list[dict[str, Any]]:
    # Atomic scientific quantities, supporting 10^-9, 1e-9, and 2.5 x 10^{-10}.
    # Restrict plain-number units so prose such as "1 was" is never an anchor.
    unit_name = r"(?:MeV|GeV|keV|eV|seconds?|sec|kg|g(?:/cm(?:\^?3)?)?|cm(?:\^?3)?|K|Hz|nm|mm|m|J|Pa|s)\b"
    latex_unit = r"\\mathrm\{(?:MeV|GeV|keV|eV|seconds?|sec|kg|g(?:/cm(?:\^?3)?)?|cm(?:\^?3)?|K|Hz|nm|mm|m|J|Pa|s)\}"
    unit = rf"(?:\s*(?:{latex_unit}|{unit_name}))?"
    patterns = (
        # Optional coefficient covers both 10^-9 and 2.5 x 10^-9.
        re.compile(r"(?<![\w.])(?:(?:[+-]?\d+(?:\.\d+)?)\s*(?:x|×|\\times|\*)\s*)?10\s*\^\s*(?:\{\s*[+-]?\d+\s*\}|[+-]?\d+)" + unit, re.I),
        re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?\s*[eE]\s*[+-]?\d+" + unit, re.I),
        re.compile(rf"(?<![\w^])[+-]?\d+(?:\.\d+)?\s*(?:{latex_unit}|{unit_name})", re.I),
    )
    found: list[dict[str, Any]] = []
    for pattern in patterns:
        found.extend({"start": m.start(), "end": m.end(), "text": m.group(0), "type": "numeric"} for m in pattern.finditer(stem))
    # Prefer the maximal span: keep 10^-9 sec, not its overlapping 10 or -9.
    result: list[dict[str, Any]] = []
    for item in sorted(found, key=lambda x: (x["start"], -(x["end"] - x["start"]))):
        if not any(kept["start"] <= item["start"] and kept["end"] >= item["end"] for kept in result):
            result.append(item)
    return result


def _clause_spans(stem: str) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for m in re.finditer(r"[^.;?!]{12,180}(?:[.;?!]|$)", stem, re.S):
        text = m.group(0).strip()
        if text:
            start = m.start() + m.group(0).find(text)
            spans.append({"start": start, "end": start + len(text), "text": text, "type": "text"})
    return spans


def _candidates(stem: str) -> list[dict[str, Any]]:
    choices = _numeric_spans(stem) + _clause_spans(stem)
    seen: set[tuple[int, int]] = set()
    result = []
    for item in sorted(choices, key=lambda x: (x["start"], x["end"] - x["start"])):
        key = (item["start"], item["end"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result[:24]


def _select_prompt(stem: str, candidates: list[dict[str, Any]]) -> str:
    listing = "\n".join(f"{i}. [{item['type']}] {item['text']}" for i, item in enumerate(candidates))
    return f"""Choose one exact condition from a science question for substitute verification.
The choice must be necessary for solving the question, must be a single listed
span, and must not be an answer option. Prefer one atomic numeric condition when
it is relevant. Return only the listed span id; do not rewrite its text.

Question stem:
{stem}

Candidate spans:
{listing}

Return strict JSON only:
{{"span_id": integer, "reason":"one short sentence"}}"""


def _masked_question(condition: dict[str, Any], options: str) -> str:
    stem = condition["stem"]
    masked = stem[:condition["start"]] + "[X]" + stem[condition["end"]:]
    return f"{masked}\n\n{options}".strip()


def _solve_prompt(masked_question: str, answer: str, key_type: str) -> str:
    output = "a single normalized numeric value with unit when available" if key_type == "numeric" else "the exact missing text only"
    return f"""Solve a substitute-verification task independently. You do not see any
reasoning chain. The proposed answer option is {answer}, but do not assume it is
correct. Infer the value or text that [X] must have if that option were correct.

Masked question:
{masked_question}

Return {output}. Return strict JSON only:
{{"x":"..."}}"""


def _quantity(text: str) -> tuple[Decimal, str] | None:
    value = _norm(text)
    value = value.replace("{", "").replace("}", "")
    match = re.search(r"(?:(?:([+-]?\d+(?:\.\d+)?)\s*(?:x|\*)\s*)?)10\s*\^\s*([+-]?\d+)", value)
    if match:
        try:
            coefficient = match.group(1) or "1"
            number = Decimal(coefficient) * (Decimal(10) ** int(match.group(2)))
        except (InvalidOperation, ValueError):
            return None
        suffix = value[match.end():]
    else:
        match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*e\s*([+-]?\d+)", value)
        if match:
            try:
                number = Decimal(match.group(1)) * (Decimal(10) ** int(match.group(2)))
            except (InvalidOperation, ValueError):
                return None
            suffix = value[match.end():]
        else:
            match = re.search(r"([+-]?\d+(?:\.\d+)?)", value)
            if not match:
                return None
            try:
                number = Decimal(match.group(1))
            except InvalidOperation:
                return None
            suffix = value[match.end():]
    unit = "".join(re.findall(r"[a-z]+", suffix))
    return number, unit


def _deterministic_verdict(key_type: str, condition: str, predicted: str) -> tuple[str, str]:
    if key_type == "numeric":
        left, right = _quantity(condition), _quantity(predicted)
        if left is None or right is None:
            return "UNKNOWN", "numeric_parse_failed"
        l_value, l_unit = left
        r_value, r_unit = right
        value_match = l_value == r_value
        unit_match = not l_unit or not r_unit or l_unit == r_unit
        return ("MATCH", "normalized_numeric_equal") if value_match and unit_match else ("NO_MATCH", "normalized_numeric_different")
    a, b = _norm(condition), _norm(predicted)
    if a and b and (a == b or (len(b) >= 8 and b in a) or (len(a) >= 8 and a in b)):
        return "MATCH", "exact_or_contained_text"
    return "UNKNOWN", "non_numeric_not_deterministically_comparable"


def _load_or_init(args: argparse.Namespace) -> list[dict[str, Any]]:
    path = Path(args.out)
    if path.exists():
        return _load_json(str(path))
    source = _load_json(args.source)
    records = []
    for raw in source[:args.limit]:
        record = dict(raw)
        record["shared_condition"] = {}
        record["shared_proco"] = {str(i): {} for i in range(3)}
        records.append(record)
    _save_json(args.out, records)
    return records


def run_condition(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("shared_condition", {}).get("status") in {"ready", "missing"}:
            continue
        stem, options = _stem_and_options(record["question"])
        spans = _candidates(stem)
        numeric = [i for i, item in enumerate(spans) if item["type"] == "numeric"]
        if not spans:
            record["shared_condition"] = {"status": "missing", "error": "no_candidate_span"}
            _save_json(args.out, records)
            continue
        raw, parsed = _json_call("qwen", _select_prompt(stem, spans), 180, ("span_id",))
        try:
            choice = int(parsed.get("span_id"))
        except (TypeError, ValueError):
            choice = -1
        if choice not in range(len(spans)):
            choice = numeric[0] if numeric else 0
            selection = "deterministic_fallback"
        elif numeric and spans[choice]["type"] != "numeric":
            # Numeric conditions permit deterministic matching and are mandatory
            # whenever the stem provides one; do not let a prose clause erase it.
            choice = numeric[0]
            selection = "numeric_priority_override"
        else:
            selection = "qwen_span_selector"
        chosen = dict(spans[choice])
        chosen.update({"status": "ready", "stem": stem, "options": options, "selection": selection, "selection_raw": raw, "selection_reason": str(parsed.get("reason", "")), "candidates": spans})
        record["shared_condition"] = chosen
        _save_json(args.out, records)
        print(f"[condition] {pos}/{len(records)} idx={record['idx']} {chosen['type']} {chosen['text']!r}", flush=True)


def run_verifier(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    verifier = args.model
    for pos, record in enumerate(records, 1):
        condition = record.get("shared_condition", {})
        if condition.get("status") != "ready":
            continue
        masked = _masked_question(condition, condition.get("options", ""))
        for slot, origin in enumerate(record["sampled_nodes"]):
            if origin == verifier:
                continue
            answer = record.get("initial_answers", {}).get(str(slot))
            if answer not in {"A", "B", "C", "D"}:
                continue
            evidence = record.setdefault("shared_proco", {}).setdefault(str(slot), {}).setdefault(verifier, {})
            if evidence.get("verdict") in {"MATCH", "NO_MATCH", "UNKNOWN"}:
                continue
            raw, parsed = _json_call(verifier, _solve_prompt(masked, answer, condition["type"]), 160, ("x",))
            predicted = str(parsed.get("x", "")).strip()
            verdict, reason = _deterministic_verdict(condition["type"], condition["text"], predicted)
            evidence.update({"masked_question": masked, "solve_raw": raw, "verification_answer": predicted, "verdict": verdict, "match_reason": reason})
            _save_json(args.out, records)
            print(f"[verifier {verifier}] {pos}/{len(records)} idx={record['idx']} target=M{slot} {verdict}", flush=True)


def _consensus(record: dict[str, Any], slot: int) -> dict[str, Any]:
    entries = record.get("shared_proco", {}).get(str(slot), {})
    verdicts = [item.get("verdict") for item in entries.values()]
    if len(verdicts) == 2 and all(v == "NO_MATCH" for v in verdicts):
        status = "CONFIRMED_NO_MATCH"
    elif len(verdicts) == 2 and all(v == "MATCH" for v in verdicts):
        status = "CONFIRMED_MATCH"
    elif verdicts:
        status = "MIXED_OR_INSUFFICIENT"
    else:
        status = "NO_EVIDENCE"
    return {"status": status, "entries": entries}


def _chain_block(record: dict[str, Any], slot: int, with_evidence: bool) -> str:
    answer = record.get("initial_answers", {}).get(str(slot), "N/A")
    block = f"M{slot} proposed answer: {answer}\nOriginal chain:\n{record['initial_responses'].get(str(slot), '')[:1700]}"
    if with_evidence:
        condition = record.get("shared_condition", {})
        consensus = _consensus(record, slot)
        block += f"\nShared substitute verification: {consensus['status']}"
        block += f"\nMasked condition: {condition.get('text', 'missing')}"
        for verifier, evidence in consensus["entries"].items():
            block += f"\n- {verifier}: inferred={evidence.get('verification_answer', 'missing')}; verdict={evidence.get('verdict', 'UNKNOWN')}"
    return block


def _judge_pairwise(question: str, record: dict[str, Any], with_evidence: bool) -> dict[str, Any]:
    scores = [0.0, 0.0, 0.0]
    pairs = []
    for pair_no, (a, b) in enumerate(((0, 1), (0, 2), (1, 2))):
        outcomes = []
        for reverse in (False, True):
            left_slot, right_slot = (b, a) if reverse else (a, b)
            prompt = _pairwise_prompt(question, _chain_block(record, left_slot, with_evidence), _chain_block(record, right_slot, with_evidence))
            if with_evidence:
                prompt = prompt.replace("No reference answer is provided.", "Use CONFIRMED_NO_MATCH as a concrete contradiction. Treat CONFIRMED_MATCH, MIXED_OR_INSUFFICIENT, and NO_EVIDENCE as non-decisive. No reference answer is provided.")
            raw, result = "", None
            for retry in range(3):
                raw = _call(JUDGE, prompt, 700, temperature=0.2, seed=1300 + pair_no * 10 + retry + int(reverse) * 3 + int(with_evidence) * 100)
                result = _pairwise_result(raw)
                if result:
                    break
            # Convert the reversed call back to the original a/b orientation.
            if reverse and result in {"a", "b"}:
                result = "b" if result == "a" else "a"
            outcomes.append({"reverse": reverse, "result": result or "tie_fallback", "raw": raw})
        results = [x["result"] for x in outcomes]
        if results == ["a", "a"]:
            scores[a] += 1.0
            final = "a"
        elif results == ["b", "b"]:
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
    for pos, record in enumerate(records, 1):
        for label, with_evidence in (("baseline_swap_judge", False), ("shared_judge", True)):
            if record.get(label, {}).get("answer") not in {"A", "B", "C", "D"}:
                record[label] = _judge_pairwise(record["question"], record, with_evidence)
                _save_json(args.out, records)
        print(f"[judge] {pos}/{len(records)} idx={record['idx']} P0swap={record['baseline_swap_judge'].get('answer')} shared={record['shared_judge'].get('answer')}", flush=True)


def _mcnemar_p(fixed: int, broken: int) -> float:
    total = fixed + broken
    if not total:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(min(fixed, broken) + 1)) / (2 ** total)
    return min(1.0, 2 * tail)


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    def answer(record: dict[str, Any], label: str) -> str | None:
        return record.get(label) if label == "stored_goa_answer" else record.get(label, {}).get("answer")
    labels = ("stored_goa_answer", "baseline_judge", "proco_judge", "baseline_swap_judge", "shared_judge")
    summary: dict[str, Any] = {"n": len(records), "accuracy": {}, "consensus": {}, "verifier_verdicts": {}}
    for label in labels:
        correct = sum(answer(record, label) == record["gold"] for record in records)
        summary["accuracy"][label] = {"correct": correct, "accuracy": correct / len(records)}
    for comparator in ("baseline_swap_judge", "baseline_judge", "proco_judge"):
        fixed = sum(answer(r, "shared_judge") == r["gold"] and answer(r, comparator) != r["gold"] for r in records)
        broken = sum(answer(r, "shared_judge") != r["gold"] and answer(r, comparator) == r["gold"] for r in records)
        summary[f"paired_shared_vs_{comparator}"] = {"fixed": fixed, "broken": broken, "mcnemar_exact_p": _mcnemar_p(fixed, broken)}
    consensus = [_consensus(record, i)["status"] for record in records for i in range(3)]
    summary["consensus"] = {status: consensus.count(status) for status in ("CONFIRMED_NO_MATCH", "CONFIRMED_MATCH", "MIXED_OR_INSUFFICIENT", "NO_EVIDENCE")}
    checks = [e.get("verdict") for r in records for per_chain in r.get("shared_proco", {}).values() for e in per_chain.values()]
    summary["verifier_verdicts"] = {v: checks.count(v) for v in ("MATCH", "NO_MATCH", "UNKNOWN")}
    _save_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("condition", "verifier", "judge", "summary"))
    parser.add_argument("--model", choices=PARTICIPANTS)
    parser.add_argument("--source", default="outputs/proco_keyverify_40.json")
    parser.add_argument("--out", default="outputs/proco_keyverify_shared_10.json")
    parser.add_argument("--summary", default="outputs/proco_keyverify_shared_10_summary.json")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.stage == "verifier" and not args.model:
        parser.error("--model is required for verifier")
    records = _load_or_init(args)
    if args.stage == "condition":
        run_condition(args, records)
    elif args.stage == "verifier":
        run_verifier(args, records)
    elif args.stage == "judge":
        run_judge(args, records)
    else:
        summarize(args, records)


if __name__ == "__main__":
    main()
