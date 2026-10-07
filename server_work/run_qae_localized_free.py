#!/usr/bin/env python3
"""Conflict-localized QAE for frozen free-response MATH and HumanEval."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from typing import Any

import run_qae_pooling_free as base

CLAIM_TYPES = {"definition", "assumption", "formula", "substitution", "calculation", "comparison", "specification"}
ROUTES = {"numeric", "symbolic", "fact", "necessity", "counterexample", "specification"}


def norm(value: Any, limit: int = 10000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def initialise(args: argparse.Namespace) -> list[dict[str, Any]]:
    records = base.initialise(args)
    changed = False
    for record in records:
        for key in ("swarm_claims", "swarm_conflict", "swarm_guard"):
            if key not in record:
                record[key] = {}
                changed = True
    if changed:
        base.save(args, records)
    return records


def claims_prompt(record: dict[str, Any]) -> str:
    attempts = "\n\n".join(f"M{slot}:\n{norm(text, 1500)}" for slot, text in record.get("initial_responses", {}).items())
    return f"""Extract atomic, checkable claims explicitly stated in the frozen attempts.
Do not solve the problem or introduce new knowledge. Each claim must include a short
exact quote from its source. Prefer definitions, assumptions, formulas,
substitutions, calculations, comparisons, or program specifications. Return at
most four claims per attempt.

Problem:
{record['problem']}

Frozen attempts:
{attempts}

Return JSON only:
{{"claims":[{{"model":"M0","type":"definition|assumption|formula|substitution|calculation|comparison|specification","claim":"atomic paraphrase","quote":"exact substring","answer_impact":"low|medium|high"}}]}}"""


def run_claims(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_claims", {}).get("status") == "DONE":
            continue
        raw, parsed = base._call_json(args.model, claims_prompt(record), 900, ("claims",), 7100 + pos)
        claims, seen = [], Counter()
        for item in parsed.get("claims", []) if isinstance(parsed.get("claims"), list) else []:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model", "")).upper().removeprefix("M")
            supplied = str(item.get("type", "")).lower()
            kind = next((part for part in supplied.split("|") if part in CLAIM_TYPES), supplied)
            quote = str(item.get("quote", "")).strip()
            if model not in record.get("initial_responses", {}) or kind not in CLAIM_TYPES or not quote or seen[model] >= 4:
                continue
            if norm(quote) not in norm(record["initial_responses"][model]):
                continue
            seen[model] += 1
            claims.append({"claim_id": f"M{model}-C{seen[model]}", "model": f"M{model}", "type": kind,
                           "claim": norm(item.get("claim"), 380), "quote": quote[:300],
                           "answer_impact": str(item.get("answer_impact", "medium")).lower()})
        record["swarm_claims"] = {"status": "DONE", "claims": claims, "raw": raw}
        base.save(args, records)
        print(f"[claims] {pos}/{len(records)} idx={record['idx']} n={len(claims)}", flush=True)


def localize_prompt(record: dict[str, Any]) -> str:
    claims = record.get("swarm_claims", {}).get("claims", [])
    rendered = "\n".join(f"{x['claim_id']} [{x['type']}]: {x['claim']} | quote: {x['quote']}" for x in claims)
    return f"""Find one earliest, upstream, answer-relevant factual disagreement
among these source-attributed claims. Different wording or omitted detail is not a
conflict. Do not choose a full solution. If a genuine conflict exists, formulate
one standalone check that resolves it. It must not mention models, chains, or
candidate answers.

Problem:
{record['problem']}

Claims:
{rendered or 'No usable claims.'}

A CONFLICT must cite claims from at least two different model labels. Two claims
from the same frozen attempt cannot form a localized disagreement.

Return JSON only:
{{"status":"CONFLICT|NO_CONFLICT|UNSUITABLE","claim_refs":["M0-C1","M1-C2"],"conflict_type":"definition|assumption|formula|substitution|calculation|comparison|specification","description":"incompatible claims","target_question":"standalone check","verification_route":"numeric|symbolic|fact|necessity|counterexample|specification"}}"""


def run_localize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_conflict", {}).get("status"):
            continue
        raw, parsed = base._call_json(args.model, localize_prompt(record), 600, ("status",), 7200 + pos)
        claims_by_id = {x["claim_id"]: x for x in record.get("swarm_claims", {}).get("claims", [])}
        refs = [str(x) for x in parsed.get("claim_refs", []) if str(x) in claims_by_id]
        source_models = {str(claims_by_id[ref].get("model", "")) for ref in refs}
        supplied_kind = str(parsed.get("conflict_type", "")).lower()
        kind = next((part for part in supplied_kind.split("|") if part in CLAIM_TYPES), supplied_kind)
        supplied_route = str(parsed.get("verification_route", "")).lower()
        route = next((part for part in supplied_route.split("|") if part in ROUTES), supplied_route)
        target = str(parsed.get("target_question", "")).strip()
        valid = str(parsed.get("status", "")).upper() == "CONFLICT" and len(refs) >= 2 and len(source_models) >= 2 and kind in CLAIM_TYPES and route in ROUTES and len(target) >= 12 and not re.search(r"\b(model|chain|attempt|candidate|which answer)\b", target, re.I)
        if valid:
            record["swarm_conflict"] = {"status": "CONFLICT", "claim_refs": refs[:3], "source_models": sorted(source_models), "description": norm(parsed.get("description"), 500), "target_question": target, "verification_route": route, "raw": raw}
            record["qae_plan"] = [{"evidence_id": "D1-E1", "type": route, "question": target, "why": f"Localized {kind} conflict", "answers": {}, "status": "PENDING", "origin": "localized_conflict"}]
        else:
            record["swarm_conflict"] = {"status": "NO_VALID_LOCALIZED_CONFLICT", "raw": raw, "claim_refs": refs, "source_models": sorted(source_models), "rejection_reason": "requires_two_distinct_source_models" if str(parsed.get("status", "")).upper() == "CONFLICT" and len(refs) >= 2 and len(source_models) < 2 else "invalid_localized_conflict"}
            record["qae_plan"] = []
        base.save(args, records)
        print(f"[localize] {pos}/{len(records)} idx={record['idx']} {record['swarm_conflict']['status']}", flush=True)


def guard_prompt(record: dict[str, Any], evidence: dict[str, Any]) -> str:
    conflict = record.get("swarm_conflict", {})
    answers = "\n".join(f"{name}: {value.get('answer', 'UNKNOWN')}" for name, value in evidence.get("answers", {}).items())
    return f"""Does this settled blind evidence directly resolve the localized conflict?
DIRECT means it distinguishes the incompatible claims under their stated conditions.
Do not select a full answer.

Conflict: {conflict.get('description', '')}
Verification question: {evidence.get('question', '')}
Blind answers:
{answers}
Settled answer: {evidence.get('normalized_answer', 'UNKNOWN')}

Return JSON only:
{{"decision":"ADMIT|REJECT","directness":"DIRECT|INDIRECT|UNRELATED","reason":"brief explanation"}}"""


def run_guard(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_guard", {}).get("status"):
            continue
        evidence = record.get("qae_ledger", {}).get("D1-E1")
        if not evidence or evidence.get("status") != "STRONG" or record.get("swarm_conflict", {}).get("status") != "CONFLICT":
            record["swarm_guard"] = {"status": "NOT_ELIGIBLE"}
        else:
            raw, parsed = base._call_json(args.model, guard_prompt(record, evidence), 280, ("decision", "directness"), 7300 + pos)
            admitted = str(parsed.get("decision", "")).upper() == "ADMIT" and str(parsed.get("directness", "")).upper() == "DIRECT"
            record["swarm_guard"] = {"status": "ADMITTED" if admitted else "REJECTED", "reason": norm(parsed.get("reason"), 400), "raw": raw}
            evidence["admitted"] = admitted
        base.save(args, records)
        print(f"[guard] {pos}/{len(records)} idx={record['idx']} {record['swarm_guard']['status']}", flush=True)


def run_pool(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("qae_final_answer"):
            continue
        options = base.candidates(record)
        if not options:
            record["qae_final_reason"] = "no_usable_candidate"
            base.save(args, records)
            continue
        hard_items = [item for item in record.get("qae_hard", {}).values() if item.get("status") == "HARD"]
        supported = {candidate_id for item in hard_items for candidate_id in item.get("supports_candidate_ids", [])}
        if len(supported) == 1:
            selected = next((item for item in options if item["id"] in supported), None)
            if selected is not None:
                record["qae_pooler"] = {"model": "programmatic", "candidate_id": selected["id"], "source": selected["source"], "evidence_ids": ["H2"], "reason": "unique_programmatic_HARD_candidate", "raw": ""}
                record["qae_final_answer"], record["qae_final_reason"] = selected["answer"], "unique_programmatic_HARD_candidate"
                base.save(args, records)
                print(f"[pool] {pos}/{len(records)} idx={record['idx']} source=HARD", flush=True)
                continue
        contradicted = {candidate_id for item in hard_items for candidate_id in item.get("contradicts_candidate_ids", [])}
        viable = [item for item in options if item["id"] not in contradicted]
        if not viable:
            viable = options
        raw, parsed = base._call_json(args.model, base.pool_prompt(record, viable), 520, ("candidate_id", "reason"), 6000 + pos)
        selected = next((item for item in viable if item["id"] == str(parsed.get("candidate_id", ""))), None)
        baseline = next((item for item in options if item["source"] == "A_pool"), None)
        ids = [str(x) for x in parsed.get("evidence_ids", []) if isinstance(x, str)]
        if selected is None:
            selected, reason = baseline or options[0], "fallback_after_pooler_parse_failure"
        elif baseline and selected["id"] != baseline["id"]:
            # A free-response fact check has no sound option-to-answer mapping.
            # It may refute a local claim but cannot itself certify an arbitrary
            # replacement program. Only the unique programmatic HARD branch
            # above may replace A_pool in this runner.
            selected, reason = baseline, "retain_A_pool_no_candidate_level_HARD_support_for_replacement"
        else:
            reason = "evidence_constrained_pooler"
        record["qae_pooler"] = {"model": args.model, "candidate_id": selected["id"], "source": selected["source"], "evidence_ids": ids, "reason": reason, "pooler_reason": str(parsed.get("reason", "")), "raw": raw}
        record["qae_final_answer"], record["qae_final_reason"] = selected["answer"], reason
        base.save(args, records)
        print(f"[pool] {pos}/{len(records)} idx={record['idx']} source={selected['source']}", flush=True)


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    base.summarize(args, records)
    summary = base.load(args.summary)
    summary["conflict_localization"] = {"claim_count": sum(len(r.get("swarm_claims", {}).get("claims", [])) for r in records), "conflict_status": dict(Counter(r.get("swarm_conflict", {}).get("status") for r in records)), "directness_guard": dict(Counter(r.get("swarm_guard", {}).get("status") for r in records)), "changed_answers": sum(r.get("qae_final_answer") != r.get("baseline_answer") for r in records)}
    base._save_json(args.summary, summary)
    print(json.dumps(summary["conflict_localization"], ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("hard", "candidate_hard", "claims", "localize", "verify", "ledger", "guard", "clean", "rebuttal", "pool", "summary"))
    parser.add_argument("--dataset", required=True, choices=("math", "humaneval"))
    parser.add_argument("--mode", required=True, choices=("math", "code"))
    parser.add_argument("--paired", required=True); parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True); parser.add_argument("--summary", required=True)
    parser.add_argument("--model", choices=base.PARTICIPANTS, default="qwen")
    parser.add_argument("--limit", type=int, default=0); parser.add_argument("--evidence-count", type=int, default=1)
    args = parser.parse_args(); records = initialise(args)
    if args.stage == "hard": base.run_hard(args, records)
    elif args.stage == "candidate_hard": base.run_candidate_hard(args, records)
    elif args.stage == "claims": run_claims(args, records)
    elif args.stage == "localize": run_localize(args, records)
    elif args.stage == "verify": base.run_verify(args, records)
    elif args.stage == "ledger": base.run_ledger(args, records)
    elif args.stage == "guard": run_guard(args, records)
    elif args.stage == "clean": base.run_solve(args, records, "qae_clean", False)
    elif args.stage == "rebuttal": base.run_solve(args, records, "qae_rebuttal", True)
    elif args.stage == "pool": run_pool(args, records)
    else: summarize(args, records)


if __name__ == "__main__":
    main()
