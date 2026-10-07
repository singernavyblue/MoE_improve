#!/usr/bin/env python3
"""QAE-Pooling + HARD for frozen free-response MATH and HumanEval subsets.

The protocol never receives a reference answer or hidden HumanEval tests while
it is generating evidence or selecting a candidate.  Those signals are used
only in the final offline summary.  HARD is deliberately conservative here:
without a whitelisted, code-owned derivation it remains UNKNOWN rather than
promoting a model-produced calculation or a generated probe to HARD evidence.
"""

from __future__ import annotations

import argparse
import doctest
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from run_qae_pooling import PARTICIPANTS, _call_json, _save_json

# The QAE runner lives in /root/GoA while frozen free-response data and its
# authoritative offline scorers are retained in the sibling baseline checkout.
sys.path.insert(0, "/root/GoA_orig")
from utils import extract_human_eval_completion, is_math_equiv, last_boxed_only_string, remove_boxed
import run_paired_multi_dataset as paired_base


def load(path: str) -> Any:
    with open(path) as handle:
        return json.load(handle)


def boxed(value: str) -> str:
    answer = remove_boxed(last_boxed_only_string(str(value or "")))
    if answer is None or not str(answer).strip():
        match = re.search(r'"answer"\s*:\s*"?([^",}]+)', str(value or ""))
        answer = match.group(1) if match else str(value or "")
    return str(answer).strip()


def normal_answer(value: str, mode: str) -> str:
    return extract_human_eval_completion(str(value or "")) if mode == "code" else boxed(str(value or ""))


def initialise(args: argparse.Namespace) -> list[dict[str, Any]]:
    out = Path(args.out)
    if out.exists():
        return load(str(out))
    paired, data = load(args.paired), load(args.data)
    records = []
    for frozen in sorted(paired, key=lambda row: int(row["idx"])):
        idx = int(frozen["idx"])
        item = data[idx]
        problem = item["prompt"] if args.mode == "code" else item["question"]
        records.append({
            "idx": idx, "dataset": args.dataset, "mode": args.mode, "problem": problem,
            "entry_point": item.get("entry_point"), "test": item.get("test"),
            "gold": item.get("gold_answer"), "baseline_answer": normal_answer(frozen.get("A_answer", ""), args.mode),
            "baseline_correct": bool(frozen.get("A_pass" if args.mode == "code" else "A_correct")),
            "initial_answers": {str(k): normal_answer(v, args.mode) for k, v in (frozen.get("initial_answers") or {}).items()},
            "initial_responses": frozen.get("initial_responses") or {},
            "qae_hard": {}, "qae_plan": [], "qae_ledger": {}, "qae_clean": {},
            "qae_rebuttal": {}, "qae_pooler": {}, "qae_final_answer": "", "qae_final_reason": "",
        })
    if args.limit > 0:
        records = records[:args.limit]
    _save_json(str(out), records)
    return records


def save(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    _save_json(args.out, records)


def plan_prompt(record: dict[str, Any]) -> str:
    kind = "Python function" if record["mode"] == "code" else "mathematics problem"
    return f"""Design two or three short, independently answerable checks for this {kind}.
The checks must target a decisive invariant, boundary condition, calculation, or
counterexample. They must not ask which candidate solution is correct and must
not mention an answer produced by another model. Do not use reference answers.

Problem:
{record['problem']}

Return JSON only:
{{"questions":[{{"id":"E1","type":"calculation|specification|counterexample","question":"standalone check","why":"what it tests"}}]}}"""


def verify_prompt(record: dict[str, Any], evidence: dict[str, Any]) -> str:
    return f"""Answer this verification question independently. Give a concrete result,
derivation, boundary case, or specification fact. Do not propose a full solution
and do not refer to candidate answers. Say UNKNOWN only when it is not decidable.

Problem:
{record['problem']}

Verification question [{evidence['evidence_id']}]:
{evidence['question']}

Return JSON only:
{{"answer":"specific result or UNKNOWN","reason":"concise justification"}}"""


def normalize_prompt(evidence: dict[str, Any]) -> str:
    responses = "\n".join(f"{name}: {value.get('answer', 'UNKNOWN')}" for name, value in evidence.get("answers", {}).items())
    return f"""Reconcile blind answers to one verification question. STRONG requires at
least two semantically equivalent, specific answers. CONFLICT means specific
answers materially disagree; otherwise UNKNOWN. Do not introduce new facts.

Question: {evidence['question']}
Blind answers:
{responses}

Return JSON only:
{{"normalized_answer":"specific answer or UNKNOWN","status":"STRONG|CONFLICT|UNKNOWN","reason":"brief comparison"}}"""


def ledger_text(record: dict[str, Any]) -> str:
    parts = []
    for evidence in record.get("qae_ledger", {}).values():
        answers = "; ".join(f"{name}={value.get('answer', 'UNKNOWN')}" for name, value in evidence.get("answers", {}).items())
        parts.append(f"{evidence['evidence_id']} [{evidence['status']}]\nQ: {evidence['question']}\nBlind answers: {answers}\nSettled: {evidence.get('normalized_answer', 'UNKNOWN')}")
    return "\n\n".join(parts) or "No usable evidence."


def solver_prompt(record: dict[str, Any], rebuttal: bool) -> str:
    if rebuttal:
        attempts = "\n\n".join(f"M{slot}: {text[:900]}" for slot, text in record.get("initial_responses", {}).items())
        context = f"Frozen attempts (may be wrong):\n{attempts}"
        role = "Act as a rebuttal solver: identify any claim inconsistent with the evidence, then solve afresh."
    else:
        context = "Do not use frozen answers or reasoning chains."
        role = "Act as a clean solver: solve from the problem and evidence only."
    if record["mode"] == "code":
        rule = "Return only the Python completion after the supplied prompt, with no Markdown or tests."
    else:
        rule = 'Your answer value must be the exact final result, without prose or \"boxed\" markup.'
    return f"""{role}

Problem:
{record['problem']}

Auditable evidence ledger:
{ledger_text(record)}

{context}

{rule}
Return JSON only:
{{"answer":"final answer or Python completion","reason":"short derivation citing evidence IDs when relevant"}}"""


def candidates(record: dict[str, Any]) -> list[dict[str, str]]:
    raw = [("A_pool", record.get("baseline_answer", ""))]
    raw += [(f"M{key}", value) for key, value in record.get("initial_answers", {}).items()]
    raw += [("clean", record.get("qae_clean", {}).get("answer", "")), ("rebuttal", record.get("qae_rebuttal", {}).get("answer", ""))]
    out, seen = [], set()
    for label, value in raw:
        value = str(value or "").strip()
        if value and value not in seen:
            out.append({"id": f"C{len(out)}", "source": label, "answer": value})
            seen.add(value)
    return out


def pool_prompt(record: dict[str, Any], choices: list[dict[str, str]]) -> str:
    rendered = "\n\n".join(f"{item['id']}:\n{item['answer'][:5000]}" for item in choices)
    return f"""Select the most evidence-consistent candidate only. Agreement, model identity,
and answer length are not evidence. Do not write a new candidate. Prefer candidates
that satisfy the settled QAE evidence; retain A_pool when evidence is insufficient
to justify a replacement.

Problem:
{record['problem']}

Evidence ledger:
{ledger_text(record)}

Anonymous candidates:
{rendered}

Return JSON only:
{{"candidate_id":"C0","evidence_ids":["E1"],"reason":"concise evidence-based selection"}}"""


def run_hard(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record["qae_hard"]:
            continue
        record["qae_hard"] = {"H1": {"evidence_id": "H1", "status": "UNKNOWN", "type": "programmatic", "reason": "no_whitelisted_free_response_rule", "supports": [], "contradicts": []}}
        save(args, records)
        print(f"[hard] {pos}/{len(records)} idx={record['idx']} status=UNKNOWN", flush=True)


_MATH_CUE = re.compile(r"(?:evaluate|compute|calculate|simplify|what is|find the value of)\s*$", re.I)
_FORBIDDEN_LATEX = re.compile(r"\\(?:begin|end|text|sum|prod|int|lim|matrix|overline|operatorname)", re.I)
_FORBIDDEN_CODE = re.compile(
    r"\b(?:open|exec|eval|compile|__import__|subprocess|socket|requests|urllib|pathlib|shutil)\b|\b(?:os|sys)\s*\.",
    re.I,
)


def _latex_to_sympy(source: str) -> Any | None:
    """Parse a deliberately small, auditable arithmetic/symbolic subset.

    This route is a whitelist: unsupported LaTex is UNKNOWN, never a guessed
    computation.  It does not use a reference answer.
    """
    try:
        import sympy as sp
    except ImportError:
        return None
    text = str(source or "").strip().strip("$")
    if not text or _FORBIDDEN_LATEX.search(text):
        return None
    text = text.replace("\\left", "").replace("\\right", "")
    text = text.replace("\\cdot", "*").replace("\\times", "*")
    text = text.replace("\\pi", "pi").replace("\\sqrt", "sqrt")
    # Resolve only flat fractions. Nested braces deliberately remain unsupported.
    fraction = re.compile(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}")
    for _ in range(8):
        updated = fraction.sub(r"(\1)/(\2)", text)
        if updated == text:
            break
        text = updated
    if "\\" in text:
        return None
    text = text.replace("{", "(").replace("}", ")").replace("^", "**")
    if not re.fullmatch(r"[0-9A-Za-z_+\-*/().,= \t]+", text):
        return None
    if "=" in text:
        return None
    try:
        return sp.sympify(text, locals={"pi": sp.pi, "sqrt": sp.sqrt, "i": sp.I}, evaluate=True)
    except (SyntaxError, TypeError, ValueError):
        return None


def _explicit_math_expression(problem: str) -> tuple[str, Any] | None:
    """Return an expression only when the prose explicitly requests its value."""
    pattern = re.compile(r"\$(.+?)\$|\\\((.+?)\\\)", re.S)
    for match in pattern.finditer(problem):
        prefix = problem[max(0, match.start() - 100):match.start()]
        if not _MATH_CUE.search(prefix):
            continue
        raw = next(group for group in match.groups() if group is not None)
        value = _latex_to_sympy(raw)
        if value is not None:
            try:
                import sympy as sp
                return raw, sp.simplify(value)
            except ImportError:
                return None
    return None


def _math_candidate_hard(record: dict[str, Any], choices: list[dict[str, str]]) -> dict[str, Any]:
    derived = _explicit_math_expression(record["problem"])
    if derived is None:
        return {"evidence_id": "H2", "status": "UNKNOWN", "type": "programmatic_sympy", "reason": "no_whitelisted_explicit_expression", "supports": [], "contradicts": []}
    raw_expression, target = derived
    try:
        import sympy as sp
    except ImportError:
        return {"evidence_id": "H2", "status": "UNKNOWN", "type": "programmatic_sympy", "reason": "sympy_unavailable", "supports": [], "contradicts": []}
    matching = []
    for choice in choices:
        candidate = _latex_to_sympy(choice["answer"])
        if candidate is not None and sp.simplify(candidate - target) == 0:
            matching.append(choice["id"])
    if len(matching) != 1:
        return {"evidence_id": "H2", "status": "UNKNOWN", "type": "programmatic_sympy", "expression": raw_expression, "computed_answer": str(target), "reason": "no_unique_candidate_equivalent_to_programmatic_result", "supports": [], "contradicts": []}
    return {
        "evidence_id": "H2", "status": "HARD", "type": "programmatic_sympy",
        "rule": "explicit_evaluate_compute_or_simplify_expression", "expression": raw_expression,
        "computed_answer": str(target), "supports": [], "contradicts": [],
        "supports_candidate_ids": matching, "contradicts_candidate_ids": [],
        "mapping_reason": "The question explicitly requests this expression; SymPy derives one unique equivalent frozen candidate.",
    }


def _public_doctest_examples(problem: str, entry_point: str | None) -> list[tuple[str, str]]:
    parser = doctest.DocTestParser()
    examples = parser.get_examples(problem)
    selected = []
    for example in examples:
        source, want = example.source.strip(), example.want
        if source and want.strip() and (not entry_point or source.startswith(entry_point + "(")):
            selected.append((source, want))
    return selected


def _run_public_examples(code: str, examples: list[tuple[str, str]]) -> tuple[bool | None, str]:
    """Execute only public prompt examples in a resource-limited child process.

    This is a conservative execution guard, not a replacement for a production
    security sandbox: unsafe imports are refused and produce UNKNOWN rather than
    a negative HARD verdict.
    """
    if _FORBIDDEN_CODE.search(code):
        return None, "unsafe_api_refused"
    runner = f'''import doctest, resource
resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
source = {code!r}
examples = {examples!r}
namespace = {{}}
exec(compile(source, "candidate.py", "exec"), namespace, namespace)
checker = doctest.OutputChecker()
for expression, expected in examples:
    actual = eval(expression, namespace, namespace)
    if not checker.check_output(expected, repr(actual) + "\\n", 0):
        raise AssertionError("public_example_failed: " + expression)
print("PUBLIC_EXAMPLES_PASS")
'''
    try:
        with tempfile.TemporaryDirectory(prefix="qae_public_examples_") as workdir:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", "-c", runner], cwd=workdir,
                text=True, capture_output=True, timeout=3,
                env={"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"},
            )
    except subprocess.TimeoutExpired:
        return False, "public_example_timeout"
    if completed.returncode == 0 and "PUBLIC_EXAMPLES_PASS" in completed.stdout:
        return True, "all_public_examples_pass"
    return False, (completed.stderr or completed.stdout or "public_example_failed").strip()[:500]


def _code_candidate_hard(record: dict[str, Any], choices: list[dict[str, str]]) -> dict[str, Any]:
    examples = _public_doctest_examples(record["problem"], record.get("entry_point"))
    if not examples:
        return {"evidence_id": "H2", "status": "UNKNOWN", "type": "programmatic_public_examples", "reason": "no_public_executable_examples", "supports": [], "contradicts": []}
    outcomes: dict[str, dict[str, Any]] = {}
    contradicted = []
    for choice in choices:
        passed, detail = _run_public_examples(choice["answer"], examples)
        outcomes[choice["id"]] = {"passed": passed, "detail": detail}
        if passed is False:
            contradicted.append(choice["id"])
    if not contradicted:
        return {"evidence_id": "H2", "status": "UNKNOWN", "type": "programmatic_public_examples", "test_count": len(examples), "outcomes": outcomes, "reason": "no_candidate_directly_violates_public_examples", "supports": [], "contradicts": []}
    return {
        "evidence_id": "H2", "status": "HARD", "type": "programmatic_public_examples",
        "rule": "public_prompt_doctest_execution", "test_count": len(examples), "outcomes": outcomes,
        "supports": [], "contradicts": [], "supports_candidate_ids": [], "contradicts_candidate_ids": contradicted,
        "mapping_reason": "A candidate that fails an explicit public example directly violates the stated task specification.",
    }


def run_candidate_hard(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    """Add candidate-level HARD constraints after clean/rebuttal candidates exist."""
    for pos, record in enumerate(records, 1):
        if "H2" in record.get("qae_hard", {}):
            continue
        choices = candidates(record)
        item = _math_candidate_hard(record, choices) if record["mode"] == "math" else _code_candidate_hard(record, choices)
        record.setdefault("qae_hard", {})["H2"] = item
        save(args, records)
        print(f"[candidate_hard] {pos}/{len(records)} idx={record['idx']} status={item['status']} rule={item.get('rule', '-')}", flush=True)


def run_plan(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record["qae_plan"]:
            continue
        plan: list[dict[str, Any]] = []
        for attempt in range(3):
            raw, parsed = _call_json(args.model, plan_prompt(record), 620, ("questions",), 1000 + pos * 10 + attempt)
            for item in parsed.get("questions", []) if isinstance(parsed.get("questions"), list) else []:
                # Some otherwise usable model JSON includes scalar placeholders
                # alongside question objects.  They are not evidence plans.
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                if question and question not in {p["question"] for p in plan}:
                    plan.append({"evidence_id": f"E{len(plan)+1}", "type": str(item.get("type", "fact")), "question": question, "why": str(item.get("why", "")), "answers": {}, "status": "PENDING", "plan_raw": raw})
                if len(plan) >= args.evidence_count:
                    break
            if len(plan) >= 2:
                break
        record["qae_plan"] = plan
        save(args, records)
        print(f"[plan] {pos}/{len(records)} idx={record['idx']} evidence={len(plan)}", flush=True)


def run_verify(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        for evidence in record["qae_plan"]:
            if evidence["answers"].get(args.model, {}).get("answer"):
                continue
            raw, parsed = _call_json(args.model, verify_prompt(record, evidence), 340, ("answer",), 2000 + pos)
            answer = str(parsed.get("answer", "")).strip() or "UNKNOWN"
            evidence["answers"][args.model] = {"answer": answer, "reason": str(parsed.get("reason", "")), "raw": raw}
            save(args, records)
            print(f"[verify {args.model}] {pos}/{len(records)} idx={record['idx']} {evidence['evidence_id']}", flush=True)


def run_ledger(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        for evidence in record["qae_plan"]:
            key = evidence["evidence_id"]
            if key in record["qae_ledger"]:
                continue
            raw, parsed = _call_json(args.model, normalize_prompt(evidence), 260, ("status",), 3000 + pos)
            status = str(parsed.get("status", "UNKNOWN")).upper()
            status = status if status in {"STRONG", "CONFLICT", "UNKNOWN"} else "UNKNOWN"
            record["qae_ledger"][key] = {"evidence_id": key, "type": evidence["type"], "question": evidence["question"], "answers": evidence["answers"], "normalized_answer": str(parsed.get("normalized_answer", "UNKNOWN")), "status": status, "reason": str(parsed.get("reason", "")), "raw": raw}
            save(args, records)
            print(f"[ledger] {pos}/{len(records)} idx={record['idx']} {key}={status}", flush=True)


def run_solve(args: argparse.Namespace, records: list[dict[str, Any]], field: str, rebuttal: bool) -> None:
    for pos, record in enumerate(records, 1):
        if record[field].get("answer"):
            continue
        raw, parsed = _call_json(args.model, solver_prompt(record, rebuttal), 900 if record["mode"] == "code" else 700, ("answer", "reason"), 5000 + pos)
        answer = normal_answer(str(parsed.get("answer", "") or raw), record["mode"])
        record[field] = {"model": args.model, "answer": answer, "reason": str(parsed.get("reason", "")), "raw": raw}
        save(args, records)
        print(f"[{field}] {pos}/{len(records)} idx={record['idx']} chars={len(answer)}", flush=True)


def run_pool(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        options = candidates(record)
        if not options:
            record["qae_final_reason"] = "no_usable_candidate"
            continue
        raw, parsed = _call_json(args.model, pool_prompt(record, options), 520, ("candidate_id", "reason"), 6000 + pos)
        wanted = str(parsed.get("candidate_id", ""))
        selected = next((item for item in options if item["id"] == wanted), None)
        evidence_ids = [str(value) for value in parsed.get("evidence_ids", []) if isinstance(value, str)]
        baseline = next((item for item in options if item["source"] == "A_pool"), None)
        strong = {key for key, item in record["qae_ledger"].items() if item.get("status") == "STRONG"}
        if selected is None:
            selected, reason = baseline or options[0], "fallback_after_pooler_parse_failure"
        elif baseline and selected["id"] != baseline["id"] and not (set(evidence_ids) & strong):
            selected, reason = baseline, "retain_A_pool_no_cited_strong_evidence"
        else:
            reason = "evidence_constrained_pooler"
        record["qae_pooler"] = {"model": args.model, "candidate_id": selected["id"], "source": selected["source"], "evidence_ids": evidence_ids, "reason": str(parsed.get("reason", "")), "raw": raw}
        record["qae_final_answer"] = selected["answer"]
        record["qae_final_reason"] = reason
        save(args, records)
        print(f"[pool] {pos}/{len(records)} idx={record['idx']} source={selected['source']}", flush=True)


def correct(record: dict[str, Any], answer: str) -> bool:
    if record["mode"] == "code":
        item = {"prompt": record["problem"], "test": record["test"], "entry_point": record["entry_point"]}
        return bool(paired_base._check_humaneval(item, answer))
    try:
        return bool(is_math_equiv(str(answer or ""), str(record.get("gold", ""))))
    except Exception:
        return False


def mcnemar(fixed: int, broken: int) -> float:
    n = fixed + broken
    return 1.0 if not n else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(fixed, broken) + 1)) / 2 ** n)


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    final_ok = [correct(record, record.get("qae_final_answer", "")) for record in records]
    baseline_ok = [bool(record["baseline_correct"]) for record in records]
    fixed = sum(not base and final for base, final in zip(baseline_ok, final_ok))
    broken = sum(base and not final for base, final in zip(baseline_ok, final_ok))
    statuses = Counter(item["status"] for record in records for item in record["qae_ledger"].values())
    hard_status = Counter(item.get("status") for record in records for item in record.get("qae_hard", {}).values())
    result = {"dataset": args.dataset, "mode": args.mode, "n": len(records), "accuracy": {"A_pool": sum(baseline_ok) / len(records) if records else None, "qae_final": sum(final_ok) / len(records) if records else None}, "paired_final_vs_A_pool": {"n": len(records), "fixed": fixed, "broken": broken, "mcnemar_exact_p": mcnemar(fixed, broken)}, "evidence_status": dict(statuses), "hard_status": dict(hard_status), "scoring": "HumanEval private unit tests" if args.mode == "code" else "MATH symbolic equivalence"}
    _save_json(args.summary, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("hard", "candidate_hard", "plan", "verify", "ledger", "clean", "rebuttal", "pool", "summary"))
    parser.add_argument("--dataset", required=True, choices=("math", "humaneval"))
    parser.add_argument("--mode", required=True, choices=("math", "code"))
    parser.add_argument("--paired", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--model", choices=PARTICIPANTS, default="qwen")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--evidence-count", type=int, default=3)
    args = parser.parse_args()
    records = initialise(args)
    {"hard": run_hard, "candidate_hard": run_candidate_hard, "plan": run_plan, "verify": run_verify, "ledger": run_ledger, "pool": run_pool, "summary": summarize}.get(args.stage, lambda *_: run_solve(args, records, "qae_clean" if args.stage == "clean" else "qae_rebuttal", args.stage == "rebuttal"))(args, records)


if __name__ == "__main__":
    main()
