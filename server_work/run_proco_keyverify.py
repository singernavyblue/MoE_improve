#!/usr/bin/env python3
"""Paired ProCo-style key-condition verification on frozen GPQA chains.

This runner deliberately separates model stages so one GPU can serve a single
model at a time.  It evaluates exactly the same frozen three-model chains in
two conditions:
  P0: an independent judge selects a chain from the original chains only;
  P1: the judge receives the ProCo key-condition verification evidence first.

No gold answer is sent to a participant or to the judge.  Gold is used only
for the final paired evaluation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from endpoint import model_endpoint_dict
from utils import generate_vllm


PARTICIPANTS = ("qwen", "mathstral", "biomedical_llama")
JUDGE = "prometheus"
ENDPOINT = "http://127.0.0.1:8000/v1/completions"


def _load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def _save_json(path: str, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _parse_json_loose(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    text = str(text).strip()
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(.*?)```", text, re.S | re.I))
    candidates.extend(re.findall(r"(\{.*?\})", text, re.S))
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            # LLMs often put LaTex such as `\,` or `\text` inside JSON strings.
            # Escape only invalid JSON backslashes, preserving valid JSON escapes.
            try:
                repaired = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", candidate.strip())
                value = json.loads(repaired)
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    return None


def _letter(value: Any) -> str | None:
    if value is None:
        return None
    matches = re.findall(r"(?:answer|choice|option)\\s*(?:is|:|=)?\\s*\\(?([A-D])\\)?|\\(([A-D])\\)", str(value), re.I)
    if matches:
        return next((a or b for a, b in matches[::-1] if a or b), None).upper()
    direct = re.findall(r"\\b([A-D])\\b", str(value).upper())
    return direct[-1] if direct else None


def _winner(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("winner") or value.get("selected_chain") or value.get("choice")
        direct = re.fullmatch(r"\s*M?([0-2])\s*", str(value), re.I)
        if direct:
            return int(direct.group(1))
    match = re.search(r"(?:\[WINNER\]|final winner|winner)\s*[:=-]?\s*M?([0-2])\b", str(value), re.I)
    return int(match.group(1)) if match else None


def _call(model_key: str, prompt: str, max_tokens: int, temperature: float = 0.2, seed: int = 42) -> str:
    cfg = model_endpoint_dict[model_key]
    answer, _, _, _, _ = generate_vllm(
        model=cfg["model_id"],
        messages=[{"role": "user", "content": prompt}],
        endpoint=ENDPOINT,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
        debug_txt=f"[ProCo {model_key}] ",
    )
    return answer or ""


def _json_call(model_key: str, prompt: str, max_tokens: int, required: tuple[str, ...]) -> tuple[str, dict[str, Any]]:
    """Retry the small structured calls: Mistral-family models occasionally emit only `{` greedily."""
    last_raw = ""
    best_raw = ""
    for _ in range(2):
        last_raw = _call(model_key, prompt, max_tokens, temperature=0.7, seed=42 + _)
        if len(last_raw.strip()) > len(best_raw.strip()):
            best_raw = last_raw
        parsed = _parse_json_loose(last_raw) or {}
        if all(str(parsed.get(key, "")).strip() for key in required):
            return last_raw, parsed
    return best_raw or last_raw, _parse_json_loose(best_raw or last_raw) or {}


def _key_prompt(question: str, chain: str) -> str:
    return f"""You are applying key-condition verification (ProCo) to audit a proposed
solution to a graduate-level science multiple-choice question.

Original question:
{question}

Proposed reasoning chain:
{chain[:2200]}

Identify ONE concrete condition from the original question that is necessary for
this chain's conclusion. Do not choose an answer letter, style feature, or
model confidence. Construct a standalone verification question by masking that
condition as [X] and conditioning on the proposed conclusion. The question
must be objectively answerable without the answer options.

Use key_type="numeric" only when the key condition is a number, magnitude,
coefficient, count, or equation value; otherwise use key_type="proposition"
for a factual/entity/concept relation. For proposition, the verification
question must yield a clear true/false or a specific factual value.

Return strict JSON only:
{{"key_type":"numeric" or "proposition", "key_condition":"the exact masked condition", "verification_question":"question containing [X]", "why_necessary":"one short sentence"}}"""


def _solve_prompt(question: str, chain: str, verification_question: str, key_type: str) -> str:
    answer_shape = "an exact normalized numeric value with any essential unit" if key_type == "numeric" else "a concise factual value or true/false"
    return f"""Solve a verification question independently as part of a ProCo audit.
Do not assume that the original proposed solution is correct, and do not use
answer-choice letters. Give {answer_shape}.

Original problem:
{question}

Original proposed chain (context only; it may be wrong):
{chain[:1800]}

Verification question:
{verification_question}

Return strict JSON only:
{{"verification_answer":"...", "reason":"one or two factual sentences"}}"""


def _match_prompt(key_type: str, key_condition: str, verification_question: str, predicted: str) -> str:
    if key_type == "numeric":
        rule = "Decide whether the numerical value (including sign, exponent, coefficient, and unit where relevant) is exactly equivalent."
    else:
        rule = "Decide the proposition: if the verification question's answer is the original key condition, could [X] also be the independently predicted value? Treat incompatible entities, facts, or truth values as NO_MATCH."
    return f"""Perform the final ProCo key-condition check. {rule}

Key condition from the original question: {key_condition}
Verification question: {verification_question}
Independent predicted answer: {predicted}

Return strict JSON only:
{{"verdict":"MATCH" or "NO_MATCH", "reason":"one short sentence"}}"""


def _chain_block(record: dict[str, Any], i: int, with_evidence: bool) -> str:
    chains = record["initial_responses"]
    answers = record["initial_answers"]
    evidence = record.get("proco", {}).get(str(i), {})
    block = f"M{i} ({record['sampled_nodes'][i]}) proposed answer: {answers.get(str(i), 'N/A')}\\nOriginal chain:\n{chains.get(str(i), '')[:1700]}"
    if with_evidence:
        block += ("\\nKey-condition verification evidence:\n"
                  f"- type: {evidence.get('key_type', 'missing')}\\n"
                  f"- masked key condition: {evidence.get('key_condition', 'missing')}\\n"
                  f"- verification question: {evidence.get('verification_question', 'missing')}\\n"
                  f"- independent answer: {evidence.get('verification_answer', 'missing')}\\n"
                  f"- check: {evidence.get('verdict', 'missing')} ({evidence.get('match_reason', '')})")
    return block


def _chains_block(record: dict[str, Any], with_evidence: bool) -> str:
    return "\\n\\n".join(_chain_block(record, i, with_evidence) for i in range(3))


def _pairwise_prompt(question: str, response_a: str, response_b: str) -> str:
    return f"""###Task Description:
An instruction, two responses, and evaluation criteria are given.
Compare Response A and Response B strictly by factual accuracy, logical
soundness, and whether they answer the question. Do not prefer length or
confidence. No reference answer is provided.
Write concise feedback, then end with exactly `[RESULT] A`, `[RESULT] B`, or
`[RESULT] tie`. Do not omit the marker.

###Instruction:
{question}

###Response A:
{response_a}

###Response B:
{response_b}

###Feedback:
"""


def _judge_prompt(question: str, record: dict[str, Any], with_evidence: bool) -> str:
    evidence_rule = ("Use each key-condition check as diagnostic evidence: a NO_MATCH is a concrete contradiction and should count against that chain; a MATCH is supportive but not proof. " if with_evidence else "")
    return f"""You are an independent adjudicator for a graduate-level science multiple-choice problem.
Choose which of three frozen proposed chains is most likely correct. You do not
know the gold answer. Ignore response length, fluency, and self-reported
confidence. Evaluate factual consistency and reasoning only. {evidence_rule}
Do not synthesize a new answer: select one original chain.

Question:
{question}

{_chains_block(record, with_evidence)}

Return strict JSON only:
{{"winner":"M0" or "M1" or "M2", "reason":"two short sentences"}}"""


def _selected_records(source_path: str, question_path: str, limit: int) -> list[dict[str, Any]]:
    source = _load_json(source_path)
    questions = _load_json(question_path)
    qmap = {i: item["question"] for i, item in enumerate(questions)}
    chosen = []
    for raw in sorted(source, key=lambda x: x["idx"]):
        if set(raw.get("sampled_nodes", [])) != set(PARTICIPANTS):
            continue
        if len(raw.get("sampled_nodes", [])) != 3 or len(set(raw["sampled_nodes"])) != 3:
            continue
        chains = {str(k): v for k, v in raw["initial_responses"].items()}
        answers = {str(k): v for k, v in raw.get("initial_answers", {}).items()}
        chosen.append({
            "idx": raw["idx"], "question": qmap[raw["idx"]], "gold": raw["gold"],
            "sampled_nodes": raw["sampled_nodes"], "initial_responses": chains,
            "initial_answers": answers, "stored_goa_answer": raw.get("A", {}).get("answer"),
            "proco": {},
        })
        if len(chosen) >= limit:
            break
    if len(chosen) != limit:
        raise ValueError(f"needed {limit} fixed triples, found {len(chosen)}")
    return chosen


def _load_or_init(args: argparse.Namespace) -> list[dict[str, Any]]:
    if Path(args.out).exists():
        return _load_json(args.out)
    records = _selected_records(args.source, args.questions, args.limit)
    _save_json(args.out, records)
    return records


def run_participant(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    model_key = args.model
    for pos, rec in enumerate(records, 1):
        slot = rec["sampled_nodes"].index(model_key)
        evidence = rec.setdefault("proco", {}).setdefault(str(slot), {})
        if evidence.get("verdict") in {"MATCH", "NO_MATCH"}:
            continue
        if not evidence.get("verification_question"):
            raw, parsed = _json_call(model_key, _key_prompt(rec["question"], rec["initial_responses"][str(slot)]), 420, ("key_type", "key_condition", "verification_question"))
            evidence.update({
                "key_raw": raw, "key_type": str(parsed.get("key_type", "proposition")).lower(),
                "key_condition": str(parsed.get("key_condition", "")),
                "verification_question": str(parsed.get("verification_question", "")),
                "why_necessary": str(parsed.get("why_necessary", "")),
            })
        if not evidence.get("verification_question"):
            evidence["error"] = "key_question_parse_failed"
            _save_json(args.out, records)
            continue
        if not evidence.get("verification_answer"):
            raw, parsed = _json_call(model_key, _solve_prompt(rec["question"], rec["initial_responses"][str(slot)], evidence["verification_question"], evidence["key_type"]), 360, ("verification_answer",))
            fallback_answer = ""
            if not parsed and raw:
                match = re.search(r"verification\s+answer\s*[:=-]\s*(.+)", raw, re.I | re.S)
                fallback_answer = (match.group(1) if match else raw).strip()
            evidence.update({"solve_raw": raw, "verification_answer": str(parsed.get("verification_answer", "")), "solve_reason": str(parsed.get("reason", ""))})
            if not evidence["verification_answer"] and fallback_answer:
                evidence["verification_answer"] = fallback_answer[:600]
                evidence["solve_reason"] = "unstructured_model_answer"
        if not evidence.get("verification_answer"):
            evidence["error"] = "verification_answer_parse_failed"
            _save_json(args.out, records)
            continue
        raw, parsed = _json_call(model_key, _match_prompt(evidence["key_type"], evidence["key_condition"], evidence["verification_question"], evidence["verification_answer"]), 180, ("verdict",))
        verdict = str(parsed.get("verdict", "")).upper()
        if verdict not in {"MATCH", "NO_MATCH"}:
            if re.search(r"\bNO[_ -]?MATCH\b|\bincorrect\b", raw, re.I):
                verdict = "NO_MATCH"
            elif re.search(r"\bMATCH\b|\bcorrect\b", raw, re.I):
                verdict = "MATCH"
        evidence.update({"match_raw": raw, "verdict": verdict if verdict in {"MATCH", "NO_MATCH"} else "UNKNOWN", "match_reason": str(parsed.get("reason", ""))})
        _save_json(args.out, records)
        print(f"[participant {model_key}] {pos}/{len(records)} idx={rec['idx']} slot=M{slot} {evidence['verdict']}", flush=True)


def _pairwise_result(text: str) -> str | None:
    if not text:
        return None
    marker = re.search(r"\[RESULT\]\s*(A|B|tie)\b", text, re.I)
    return marker.group(1).lower() if marker else None


def _judge_pairwise(question: str, record: dict[str, Any], with_evidence: bool) -> dict[str, Any]:
    """Use Prometheus in its native pairwise format; a 3-way JSON winner is unreliable."""
    scores = [0.0, 0.0, 0.0]
    pairs = []
    for pair_no, (a, b) in enumerate(((0, 1), (0, 2), (1, 2))):
        block_a = _chain_block(record, a, with_evidence)
        block_b = _chain_block(record, b, with_evidence)
        raw = ""
        result = None
        for retry in range(3):
            raw = _call(JUDGE, _pairwise_prompt(question, block_a, block_b), 700, temperature=0.2, seed=100 + pair_no + retry)
            result = _pairwise_result(raw)
            if result is not None:
                break
        if result == "a":
            scores[a] += 1.0
        elif result == "b":
            scores[b] += 1.0
        else:
            result = result or "tie_fallback"
            scores[a] += 0.5
            scores[b] += 0.5
        pairs.append({"pair": [a, b], "result": result, "raw": raw})
    winner = max(range(3), key=lambda i: (scores[i], -i))
    return {"winner": winner, "answer": record["initial_answers"].get(str(winner)), "scores": scores, "pairs": pairs}


def run_judge(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    def one(rec: dict[str, Any]) -> dict[str, Any]:
        for label, evidence in (("baseline_judge", False), ("proco_judge", True)):
            if rec.get(label, {}).get("answer") in {"A", "B", "C", "D"}:
                continue
            rec[label] = _judge_pairwise(rec["question"], rec, evidence)
        return rec

    pending = [i for i, rec in enumerate(records) if rec.get("proco_judge", {}).get("answer") not in {"A", "B", "C", "D"}]
    with ThreadPoolExecutor(max_workers=args.judge_workers) as executor:
        futures = {executor.submit(one, records[i]): i for i in pending}
        for done, future in enumerate(as_completed(futures), 1):
            i = futures[future]
            records[i] = future.result()
            _save_json(args.out, records)
            rec = records[i]
            print(f"[judge] {done}/{len(pending)} idx={rec['idx']} P0={rec['baseline_judge'].get('answer')} P1={rec['proco_judge'].get('answer')}", flush=True)


def _mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    def correct(key: str, r: dict[str, Any]) -> bool:
        if key == "stored_goa_answer":
            answer = r.get(key)
        else:
            answer = r.get(key, {}).get("answer")
        return answer == r["gold"]
    labels = ("stored_goa_answer", "baseline_judge", "proco_judge")
    summary: dict[str, Any] = {"n": len(records), "accuracy": {}}
    for label in labels:
        n = sum(correct(label, r) for r in records)
        summary["accuracy"][label] = {"correct": n, "accuracy": n / len(records)}
    b = sum((not correct("baseline_judge", r)) and correct("proco_judge", r) for r in records)
    c = sum(correct("baseline_judge", r) and (not correct("proco_judge", r)) for r in records)
    summary["paired_p1_vs_p0"] = {"fixed": b, "broken": c, "mcnemar_exact_p": _mcnemar_p(b, c)}
    checks = [e.get("verdict") for r in records for e in r.get("proco", {}).values()]
    summary["verification_checks"] = {k: checks.count(k) for k in ("MATCH", "NO_MATCH", "UNKNOWN")}
    _save_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("participant", "judge", "summary"), required=True)
    parser.add_argument("--model", choices=PARTICIPANTS)
    parser.add_argument("--source", default="outputs/hard_full_198.json")
    parser.add_argument("--questions", default="data/test/GPQA_test.json")
    parser.add_argument("--out", default="outputs/proco_keyverify_40.json")
    parser.add_argument("--summary", default="outputs/proco_keyverify_40_summary.json")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--judge-workers", type=int, default=4)
    args = parser.parse_args()
    if args.stage == "participant" and not args.model:
        parser.error("--model is required for participant stage")
    records = _load_or_init(args)
    if args.stage == "participant":
        run_participant(args, records)
    elif args.stage == "judge":
        run_judge(args, records)
    else:
        summarize(args, records)


if __name__ == "__main__":
    main()
