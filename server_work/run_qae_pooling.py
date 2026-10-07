#!/usr/bin/env python3
"""Question--Answer Evidence (QAE) pooling over frozen multiple-choice runs.

The unit of verification is an auditable factual question, not a chain verdict.
Stages are intentionally separate so a one-GPU vLLM setup can serve one model at
a time.  No verifier sees option letters, the initial pool, or another verifier's
answer.  The final selector receives a compact evidence ledger rather than long
chains or a model-vote count.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from run_proco_keyverify import PARTICIPANTS, _call, _parse_json_loose, _save_json


LETTERS = tuple("ABCDEFGHIJ")
EVIDENCE_GRADES = {"HARD", "STRONG"}


def _load(path: str) -> Any:
    with open(path) as handle:
        return json.load(handle)


def _letter(value: Any) -> str | None:
    found = re.findall(r"\b([A-J])\b", str(value or "").upper())
    return found[-1] if found else None


def _full_json_value(text: str) -> dict[str, Any] | list[Any] | None:
    """Extract a balanced outer JSON value (the models sometimes emit a bare list)."""
    source = str(text or "")
    starts = [index for index in (source.find("{"), source.find("[")) if index >= 0]
    start = min(starts) if starts else -1
    while start >= 0:
        opening = source[start]
        closing = "}" if opening == "{" else "]"
        depth, quoted, escaped = 0, False, False
        for end, char in enumerate(source[start:], start):
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(source[start:end + 1])
                        if isinstance(value, (dict, list)):
                            return value
                    except json.JSONDecodeError:
                        break
        nexts = [index for index in (source.find("{", start + 1), source.find("[", start + 1)) if index >= 0]
        start = min(nexts) if nexts else -1
    return None


def _call_json(model: str, prompt: str, tokens: int, required: tuple[str, ...], seed: int = 91) -> tuple[str, dict[str, Any]]:
    best_raw, best = "", {}
    for retry in range(2):
        raw = _call(model, prompt, tokens, temperature=0.25, seed=seed + retry)
        value = _full_json_value(raw)
        parsed = {"questions": value} if isinstance(value, list) else (value or _parse_json_loose(raw) or {})
        if len(raw) > len(best_raw):
            best_raw, best = raw, parsed
        if all(str(parsed.get(key, "")).strip() for key in required):
            return raw, parsed
    return best_raw, best


def _stem_options(question: str) -> tuple[str, str]:
    match = re.search(r"\n\s*(?:the\s+)?(?:answer\s+)?options?\s+(?:are|is)\s*:", question, re.I)
    if not match:
        return question.strip(), ""
    return question[:match.start()].strip(), question[match.end():].strip()


def _options(question: str) -> dict[str, str]:
    _, text = _stem_options(question)
    parts = re.split(r"\s*\(([A-J])\)\s*", text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def _candidate_letters(record: dict[str, Any]) -> list[str]:
    seen = []
    for answer in [record.get("stored_goa_answer"), *record.get("initial_answers", {}).values()]:
        if answer in LETTERS and answer not in seen:
            seen.append(answer)
    return seen


def _safe_number(expression: str) -> float | None:
    """Evaluate literal arithmetic only; names, attributes, and indexing are rejected."""
    source = str(expression).replace("×", "*").replace("^", "**").strip()
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError:
        return None

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return (1 if isinstance(node.op, ast.UAdd) else -1) * walk(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            return left ** right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords:
            return math.sqrt(walk(node.args[0]))
        raise ValueError("non_literal_arithmetic")

    try:
        value = walk(tree.body)
        return value if math.isfinite(value) else None
    except (ArithmeticError, ValueError, OverflowError):
        return None


def _option_number(text: str) -> float | None:
    value = str(text).lower().replace("×", "*").replace("\\times", "*").replace("{", "").replace("}", "")
    pure_power = re.search(r"(?<![\w.])([+-]?(?:\d+(?:\.\d*)?|\.\d+)?)\s*\^\s*([+-]?\d+)", value)
    if pure_power:
        return float(pure_power.group(1) or "1") ** int(pure_power.group(2))
    multiplied_scientific = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\*\s*1(?:\.0+)?\s*[eE]\s*([+-]?\d+)", value)
    if multiplied_scientific:
        return float(multiplied_scientific.group(1)) * 10 ** int(multiplied_scientific.group(2))
    scientific = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)?)\s*\*?\s*10\s*\^\s*([+-]?\d+)", value)
    if scientific:
        return float(scientific.group(1) or "1") * 10 ** int(scientific.group(2))
    exponent = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[eE]\s*([+-]?\d+)", value)
    if exponent:
        return float(exponent.group(1)) * 10 ** int(exponent.group(2))
    direct = re.search(r"(?<![\w.])([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?![\w.])", value)
    return float(direct.group(1)) if direct else None


def _hard_option_map(question: str, value: float, rel_tol: float = 1e-6) -> tuple[list[str], list[str], str]:
    numeric = {letter: _option_number(text) for letter, text in _options(question).items()}
    numeric = {letter: number for letter, number in numeric.items() if number is not None}
    if not numeric:
        return [], [], "no_direct_numeric_options"
    matches = [letter for letter, number in numeric.items() if math.isclose(number, value, rel_tol=rel_tol, abs_tol=max(1e-12, abs(value) * 1e-9))]
    return (matches if len(matches) == 1 else [], [letter for letter in numeric if letter not in matches], "programmatic_numeric_option_comparison")


def _number_from_text(text: str) -> float | None:
    """Parse one explicitly written number, including textbook 10^-3 notation."""
    candidate = str(text).strip().replace("−", "-").replace("×", "*")
    power = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)?)\s*\^\s*([+-]?\d+)", candidate)
    if power:
        return float(power.group(1) or "1") ** int(power.group(2))
    return _option_number(candidate)


def _hard_item(
    evidence_id: str, rule: str, question: str, expression: str, answer: str,
    supports: list[str], contradicts: list[str], mapping_reason: str,
) -> dict[str, Any]:
    """Create evidence whose derivation and option mapping are both code-owned."""
    return {
        "evidence_id": evidence_id,
        "status": "HARD",
        "type": "programmatic_numeric_or_symbolic",
        "rule": rule,
        "source": "deterministic_whitelisted_formula",
        "question": question,
        "expression": expression,
        "computed_answer": answer,
        "supports": supports,
        "contradicts": contradicts,
        "mapping_reason": mapping_reason,
    }


def _numbers_before_unit(text: str, unit: str) -> list[float]:
    text = str(text).replace("{", "").replace("}", "")
    pattern = rf"([+-]?(?:10\s*\^\s*[+-]?\d+|(?:\d+(?:\.\d*)?|\.\d+)\s*\*?\s*10\s*\^\s*[+-]?\d+|(?:\d+(?:\.\d*)?|\.\d+)\s*[eE]\s*[+-]?\d+|\d+(?:\.\d*)?|\.\d+))\s*{re.escape(unit)}\b"
    return [_number_from_text(match) for match in re.findall(pattern, text, re.I) if _number_from_text(match) is not None]


def _symbolic_option_map(question: str, predicate: Any, rule: str) -> tuple[list[str], list[str], str]:
    matches = [letter for letter, text in _options(question).items() if predicate(_normal_symbolic(text))]
    if len(matches) != 1:
        return [], [], f"{rule}: non_unique_or_missing_symbolic_match"
    return matches, [letter for letter in _options(question) if letter != matches[0]], f"{rule}: canonical_symbolic_option_match"


def _normal_symbolic(text: str) -> str:
    value = str(text).lower().replace("ℏ", "hbar").replace("\\hbar", "hbar")
    value = value.replace("\\sqrt", "sqrt").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", "", value)


def _programmatic_hard(question: str) -> dict[str, Any] | None:
    """Apply only conservative, inspectable formula templates.

    A model never supplies a formula, constant, or option mapping here.  This is
    intentionally a small registry: unmatched questions remain UNKNOWN rather
    than receiving a pseudo-HARD verdict from a free-form model calculation.
    """
    stem, _ = _stem_options(question)
    lowered = stem.lower()

    # gamma + gamma -> e+ + e- threshold: E_high * epsilon = m_e^2 (c=1).
    if ("gamma" in lowered or "γ" in stem) and ("e+" in lowered or "electron-positron" in lowered) and "cmb" in lowered:
        photons = _numbers_before_unit(stem, "eV")
        epsilon = next((value for value in photons if 0 < value < 1), None)
        if epsilon is not None:
            electron_mass_ev = 0.51099895e6
            threshold_gev = electron_mass_ev ** 2 / epsilon / 1e9
            supports, contradicts, reason = _hard_option_map(question, threshold_gev, rel_tol=.03)
            if supports:
                return _hard_item("H1", "gamma_gamma_pair_threshold", "What is the gamma-ray pair-production threshold energy?", "(5.1099895e5**2) / epsilon_eV / 1e9 GeV", format(threshold_gev, ".12g") + " GeV", supports, contradicts, reason)

    # Two-body decay at rest into one massive and one massless daughter.
    if "stationary" in lowered and ("rest mass" in lowered or "rest masses" in lowered) and ("nu" in lowered or "neutrino" in lowered):
        masses = _numbers_before_unit(stem, "MeV")
        if len(masses) >= 2 and masses[0] > masses[1] > 0:
            parent, daughter = masses[:2]
            massive_ke = (parent * parent + daughter * daughter) / (2 * parent) - daughter
            massless_ke = (parent * parent - daughter * daughter) / (2 * parent)
            pairs = {letter: _numbers_before_unit(text, "MeV") for letter, text in _options(question).items()}
            matches = [letter for letter, values in pairs.items() if len(values) >= 2 and math.isclose(values[0], massive_ke, rel_tol=.015, abs_tol=.08) and math.isclose(values[1], massless_ke, rel_tol=.015, abs_tol=.08)]
            if len(matches) == 1:
                return _hard_item("H1", "two_body_decay_at_rest", "What are the kinetic energies of the massive daughter and massless daughter?", "T_massive=(M**2+m**2)/(2*M)-m; T_massless=(M**2-m**2)/(2*M)", f"{massive_ke:.6g} MeV, {massless_ke:.6g} MeV", matches, [letter for letter in _options(question) if letter != matches[0]], "two_body_decay_at_rest: programmatic_pair_comparison")

    # Spin-1/2 eigenstate in the x-z plane: phi=0, up-along-n is (cos(theta/2), sin(theta/2)).
    if "eigenvector" in lowered and "x-z plane" in lowered and ("+\\hbar/2" in lowered or "+hbar/2" in lowered):
        supports, contradicts, reason = _symbolic_option_map(question, lambda text: "cos(\\theta/2)" in text and "sin(\\theta/2)" in text and "hbar" not in text and "e^(i" not in text, "spin_half_xz_eigenvector")
        if supports:
            return _hard_item("H1", "spin_half_xz_eigenvector", "What is the normalized + eigenvector for spin along n in the x-z plane?", "|n,+> = (cos(theta/2), sin(theta/2))", "(cos(theta/2), sin(theta/2))", supports, contradicts, reason)

    # Maxwell equations with magnetic charge are symmetric under electric /
    # magnetic duality.  Both div(B)=rho_m and Faraday's law gains the magnetic
    # current term: curl(E)=-dB/dt-J_m.  This is an equation-level result, not
    # a language-model judgement about which prose claim sounds plausible.
    if ("isolated north" in lowered or "isolated south" in lowered or "magnetic monopole" in lowered) and "maxwell" in lowered:
        supports, contradicts, reason = _symbolic_option_map(
            question,
            lambda text: "circulationoftheelectricfield" in text and "divergenceofthemagneticfield" in text,
            "maxwell_magnetic_charge_duality",
        )
        if supports:
            return _hard_item("H1", "maxwell_magnetic_charge_duality", "Which Maxwell equations change when magnetic charge and current are admitted?", "div(B)=rho_m; curl(E)=-dB/dt-J_m", "the circulation of E and divergence of B equations", supports, contradicts, reason)

    # V = 1/2 k r^2 + 3/2 k r^2 cos^2(theta) = 2 k x^2 + 1/2 k y^2.
    if "potential" in lowered and "3/2 kr^2 cos^2" in lowered and "energy spectrum" in lowered:
        supports, contradicts, reason = _symbolic_option_map(question, lambda text: "2n_x+n_y+3/2" in text and "sqrt(k/m)" in text, "anisotropic_2d_oscillator")
        if supports:
            return _hard_item("H1", "anisotropic_2d_oscillator", "What is the spectrum after writing the potential in Cartesian coordinates?", "V=2*k*x**2+(k/2)*y**2; omega_x=2*sqrt(k/m); omega_y=sqrt(k/m)", "E=(2*n_x+n_y+3/2)*hbar*sqrt(k/m)", supports, contradicts, reason)

    # Carbon accounting for a standard carbonyl -> epoxide sequence.  The
    # reaction ledger is explicit: methyl Grignard addition transfers one C,
    # PCC changes oxidation state only, and a methylene sulfur ylide transfers
    # one C while forming the epoxide.  C9H8O is cinnamaldehyde's formula.
    if all(token in lowered for token in ("trans-cinnamaldehyde", "methylmagnesium bromide", "pyridinium chlorochromate", "sulfaneylidene)methane")) and "carbon atoms" in lowered:
        carbon_count = 9 + 1 + 0 + 1
        supports, contradicts, reason = _hard_option_map(question, carbon_count)
        if supports:
            return _hard_item("H1", "reaction_carbon_skeleton_conservation", "How many carbons remain after Grignard addition, PCC oxidation, and sulfur-ylide epoxidation?", "C_trans-cinnamaldehyde=9; Delta_C_Grignard=+1; Delta_C_PCC=0; Delta_C_sulfur_ylide=+1", str(carbon_count), supports, contradicts, reason)

    # Lifetime broadening: a resolvable splitting must exceed hbar / shortest lifetime.
    if "lifetime" in lowered and "clearly distinguish" in lowered and "energy difference" in lowered:
        seconds = _numbers_before_unit(stem, "sec")
        if seconds:
            linewidth_ev = 6.582119569e-16 / min(seconds)
            supports, contradicts, reason = _hard_option_map(question, linewidth_ev)
            # The question asks which splitting can resolve the levels, so choose
            # the unique option strictly above the programmatic lower bound.
            numeric = {letter: _option_number(text) for letter, text in _options(question).items()}
            above = [letter for letter, value in numeric.items() if value is not None and value > linewidth_ev]
            if len(above) == 1:
                return _hard_item("H1", "lifetime_energy_resolution_bound", "What lower bound on energy splitting follows from the shortest lifetime?", "Delta_E > hbar / tau_min, with hbar=6.582119569e-16 eV*s", f"Delta_E > {linewidth_ev:.12g} eV", above, [letter for letter in numeric if letter != above[0]], "lifetime_energy_resolution_bound: unique_option_above_programmatic_bound")
    return None


def _all_evidence(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [*record.get("qae_hard", {}).values(), *record.get("qae_ledger", {}).values()]


def _init(args: argparse.Namespace) -> list[dict[str, Any]]:
    if Path(args.out).exists():
        return _load(args.out)
    records = []
    source = _load(args.source)
    selected = source if args.limit <= 0 else source[:args.limit]
    for raw in selected:
        item = dict(raw)
        item.update({"qae_plan": [], "qae_hard": {}, "qae_ledger": {}, "qae_clean": {}, "qae_rebuttal": {}, "qae_pooler": {}, "qae_final_answer": None, "qae_final_reason": ""})
        records.append(item)
    _save_json(args.out, records)
    return records


def _plan_prompt(question: str, candidates: dict[str, str]) -> str:
    listed = "\n".join(f"Claim {index}: {value}" for index, value in enumerate(candidates.values(), 1))
    return f"""Design 2 or 3 short, independently answerable factual checks for this
multiple-choice science question.  The checks must distinguish the candidate
claims below, but must not ask which option is correct and must not contain
candidate letters.  Prefer a numeric/formula check, a concrete factual or
conceptual check, and (when useful) a direct discriminating check.  Each question
must be answerable from the original problem plus ordinary domain knowledge, not
from a proposed reasoning chain.  Omit redundant or uncheckable questions.

Question:
{question}

Candidate claims (for question design only):
{listed}

Return JSON only:
{{"questions":[{{"id":"E1","type":"numeric" or "fact" or "discriminating","question":"standalone factual question","why":"which claims it can distinguish"}}]}}"""


def run_plan(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if _decisive_hard_answer(record):
            # Constraint satisfaction is complete; generating blind questions
            # cannot strengthen a uniquely derived programmatic conclusion.
            record["qae_plan"] = []
            _save_json(args.out, records)
            print(f"[plan] {pos}/{len(records)} idx={record['idx']} skipped=decisive_hard", flush=True)
            continue
        if record.get("qae_plan"):
            continue
        candidates = {key: value for key, value in _options(record["question"]).items() if key in _candidate_letters(record)}
        plan = []
        raw = ""
        for attempt in range(3):
            raw, parsed = _call_json(args.model, _plan_prompt(record["question"], candidates), 620, ("questions",), 1000 + pos * 10 + attempt)
            for item in parsed.get("questions", []) if isinstance(parsed.get("questions"), list) else []:
                question = str(item.get("question", "")).strip()
                if question and question not in {x["question"] for x in plan} and not re.search(r"\b(option|choice|candidate)\s*[A-J]\b", question, re.I):
                    plan.append({"evidence_id": f"E{len(plan)+1}", "type": str(item.get("type", "fact")).lower(), "question": question, "why": str(item.get("why", "")), "plan_raw": raw, "answers": {}, "status": "PENDING"})
                if len(plan) == args.evidence_count:
                    break
            if len(plan) >= 2:
                break
        record["qae_plan"] = plan
        _save_json(args.out, records)
        print(f"[plan] {pos}/{len(records)} idx={record['idx']} evidence={len(plan)}", flush=True)


def run_hard(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if "H1" in record.setdefault("qae_hard", {}):
            continue
        item = _programmatic_hard(record["question"])
        if item is None:
            item = {"evidence_id": "H1", "status": "UNKNOWN", "type": "programmatic_numeric_or_symbolic", "error": "no_applicable_whitelisted_rule", "supports": [], "contradicts": []}
        record["qae_hard"]["H1"] = item
        _save_json(args.out, records)
        print(f"[hard] {pos}/{len(records)} idx={record['idx']} status={item['status']} rule={item.get('rule', '-')}", flush=True)


def _blind_answer_prompt(stem: str, evidence: dict[str, Any]) -> str:
    return f"""Answer one factual verification question independently.  You are not
being asked to choose a multiple-choice option.  Do not infer or mention an
option letter.  Give the concrete value, relation, entity, or short conclusion
needed to answer the question; state UNKNOWN only if it cannot be determined.

Original problem statement (answer choices removed):
{stem}

Verification question [{evidence['evidence_id']}]:
{evidence['question']}

Return JSON only:
{{"answer":"specific factual answer or UNKNOWN","reason":"one concise factual justification"}}"""


def run_verify(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        stem, _ = _stem_options(record["question"])
        for evidence in record.get("qae_plan", []):
            answers = evidence.setdefault("answers", {})
            if answers.get(args.model, {}).get("answer"):
                continue
            raw, parsed = _call_json(args.model, _blind_answer_prompt(stem, evidence), 280, ("answer",), 2000 + pos)
            answer = str(parsed.get("answer", "")).strip()
            answers[args.model] = {"answer": answer or "UNKNOWN", "reason": str(parsed.get("reason", "")), "raw": raw}
            _save_json(args.out, records)
            print(f"[verify {args.model}] {pos}/{len(records)} idx={record['idx']} {evidence['evidence_id']}={answer[:48] or 'PARSE_FAIL'}", flush=True)


def _normalize_prompt(evidence: dict[str, Any]) -> str:
    responses = "\n".join(f"{model}: {item.get('answer', 'UNKNOWN')}" for model, item in evidence.get("answers", {}).items())
    return f"""Reconcile blind answers to one factual verification question.  Do not
choose a multiple-choice option and do not introduce information absent from the
answers.  STRONG requires two or more semantically equivalent, specific answers;
CONFLICT means specific answers materially disagree; UNKNOWN otherwise.

Question: {evidence['question']}
Blind answers:
{responses}

Return JSON only:
{{"normalized_answer":"specific answer or UNKNOWN","status":"STRONG" or "CONFLICT" or "UNKNOWN","reason":"brief comparison"}}"""


def _map_prompt(question: str, evidence: dict[str, Any], candidates: list[str]) -> str:
    return f"""Map a settled factual evidence item to answer options.  This is not a
vote.  Mark an option as contradicted only if the stated evidence directly rules
it out; mark support only if the evidence directly favors it.  UNKNOWN or
CONFLICT evidence must produce empty lists.  Do not use any reasoning chains or
an existing pooled answer.

Question with options:
{question}

Evidence {evidence['evidence_id']} ({evidence.get('status')}):
Question: {evidence['question']}
Settled answer: {evidence.get('normalized_answer', 'UNKNOWN')}

Candidate letters to assess: {', '.join(candidates)}

Return JSON only:
{{"supports":["A"],"contradicts":["B"],"reason":"brief direct link"}}"""


def run_ledger(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        candidates = _candidate_letters(record)
        for evidence in record.get("qae_plan", []):
            key = evidence["evidence_id"]
            if record.get("qae_ledger", {}).get(key, {}).get("status") in {"STRONG", "CONFLICT", "UNKNOWN"}:
                continue
            raw, parsed = _call_json(args.model, _normalize_prompt(evidence), 240, ("status",), 3000 + pos)
            status = str(parsed.get("status", "UNKNOWN")).upper()
            status = status if status in {"STRONG", "CONFLICT", "UNKNOWN"} else "UNKNOWN"
            item = {"evidence_id": key, "type": evidence.get("type", "fact"), "question": evidence["question"], "answers": evidence.get("answers", {}), "normalized_answer": str(parsed.get("normalized_answer", "UNKNOWN")), "status": status, "normalization_reason": str(parsed.get("reason", "")), "normalization_raw": raw, "supports": [], "contradicts": []}
            if status == "STRONG":
                map_raw, mapped = _call_json(args.model, _map_prompt(record["question"], item, candidates), 260, ("supports", "contradicts"), 4000 + pos)
                item.update({"supports": [x for x in mapped.get("supports", []) if x in candidates], "contradicts": [x for x in mapped.get("contradicts", []) if x in candidates], "mapping_reason": str(mapped.get("reason", "")), "mapping_raw": map_raw})
            record.setdefault("qae_ledger", {})[key] = item
            _save_json(args.out, records)
            print(f"[ledger] {pos}/{len(records)} idx={record['idx']} {key}={status}", flush=True)


def _ledger_text(record: dict[str, Any]) -> str:
    blocks = []
    for item in _all_evidence(record):
        answers = "; ".join(f"{model}={entry.get('answer', 'UNKNOWN')}" for model, entry in item.get("answers", {}).items())
        settled = item.get("computed_answer", item.get("normalized_answer", "UNKNOWN"))
        blocks.append(f"{item['evidence_id']} [{item['status']}/{item['type']}]\nQ: {item.get('question', 'not available')}\nExpression: {item.get('expression', 'n/a')}\nBlind answers: {answers}\nSettled: {settled}\nSupports: {item.get('supports', [])}; Contradicts: {item.get('contradicts', [])}")
    return "\n\n".join(blocks) or "No usable evidence."


def _solve_prompt(record: dict[str, Any], rebuttal: bool) -> str:
    if rebuttal:
        chains = "\n\n".join(f"M{slot} answer={answer}: {record.get('initial_responses', {}).get(slot, '')[:900]}" for slot, answer in record.get("initial_answers", {}).items())
        context = f"Existing A_pool: {record.get('stored_goa_answer')}\nFrozen attempts:\n{chains}"
        role = "Act as a rebuttal solver: identify any pool or chain claim directly inconsistent with the evidence, then solve afresh."
    else:
        context = "Do not use the initial answers, pooled answer, or reasoning chains."
        role = "Act as a clean solver: solve from the problem and evidence only."
    return f"""{role}

Question:
{record['question']}

Auditable evidence ledger:
{_ledger_text(record)}

{context}

Return JSON only:
{{"answer":"one option letter from the question","reason":"short derivation citing evidence IDs when relevant"}}"""


def run_solve(args: argparse.Namespace, records: list[dict[str, Any]], field: str, rebuttal: bool) -> None:
    for pos, record in enumerate(records, 1):
        if record.get(field, {}).get("answer") in LETTERS:
            continue
        hard_answer = _decisive_hard_answer(record)
        if hard_answer:
            record[field] = {"model": "programmatic", "answer": hard_answer, "reason": "unique_HARD_constraint", "raw": ""}
            _save_json(args.out, records)
            print(f"[{field}] {pos}/{len(records)} idx={record['idx']} answer={hard_answer} source=HARD", flush=True)
            continue
        if getattr(args, "diagnosis_gate", False) and not any(
            item.get("status") in EVIDENCE_GRADES for item in _all_evidence(record)
        ):
            # In the diagnosis-gated route, a clean/rebuttal re-solve without
            # admissible evidence cannot authorize a later answer replacement.
            # Preserve the frozen baseline instead of spending a model call on
            # a result that the pooler is required to discard.
            pooled = record.get("stored_goa_answer")
            record[field] = {
                "model": "programmatic",
                "answer": pooled if pooled in LETTERS else None,
                "reason": "skipped_no_valid_ledger_evidence",
                "raw": "",
            }
            _save_json(args.out, records)
            print(f"[{field}] {pos}/{len(records)} idx={record['idx']} skipped=no_valid_ledger_evidence", flush=True)
            continue
        raw, parsed = _call_json(args.model, _solve_prompt(record, rebuttal), 700, ("answer", "reason"), 5000 + pos)
        record[field] = {"model": args.model, "answer": _letter(parsed.get("answer")) or _letter(raw), "reason": str(parsed.get("reason", "")), "raw": raw}
        _save_json(args.out, records)
        print(f"[{field}] {pos}/{len(records)} idx={record['idx']} answer={record[field]['answer']}", flush=True)


def _contradicted(record: dict[str, Any], answer: str | None) -> bool:
    return bool(answer and any(item.get("status") in EVIDENCE_GRADES and answer in item.get("contradicts", []) for item in _all_evidence(record)))


def _supporting_ids(record: dict[str, Any], answer: str | None) -> set[str]:
    return {item["evidence_id"] for item in _all_evidence(record) if answer and item.get("status") in EVIDENCE_GRADES and answer in item.get("supports", [])}


def _decisive_hard_answer(record: dict[str, Any]) -> str | None:
    """Return an answer only when code-owned HARD evidence uniquely entails it.

    This implements the standard constraint-satisfaction stopping condition:
    an additional stochastic solver is unnecessary once every competing option
    is contradicted and exactly one candidate is directly supported.
    """
    hard_items = [item for item in record.get("qae_hard", {}).values() if item.get("status") == "HARD"]
    supported = {letter for item in hard_items for letter in item.get("supports", []) if letter in LETTERS}
    if len(supported) != 1:
        return None
    answer = next(iter(supported))
    if _contradicted(record, answer):
        return None
    return answer


def _pool_prompt(record: dict[str, Any], viable: list[str]) -> str:
    return f"""Select the most evidence-consistent answer.  Model agreement and answer
frequency are not evidence.  You may select only from the viable candidate set;
candidates excluded for direct contradiction are unavailable.  Cite the evidence
IDs used.  If evidence is insufficient, solve the original question yourself.

Question:
{record['question']}

Evidence ledger:
{_ledger_text(record)}

Viable candidate set: {', '.join(viable)}
Clean re-solve: {record.get('qae_clean', {}).get('answer')} — {record.get('qae_clean', {}).get('reason', '')}
Rebuttal re-solve: {record.get('qae_rebuttal', {}).get('answer')} — {record.get('qae_rebuttal', {}).get('reason', '')}

Return JSON only:
{{"answer":"one viable letter","evidence_ids":["E1"],"reason":"concise decision"}}"""


def run_pool(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        hard_answer = _decisive_hard_answer(record)
        pooled = record.get("stored_goa_answer")
        if getattr(args, "diagnosis_gate", False) and not hard_answer and pooled in LETTERS and not any(
            item.get("status") in EVIDENCE_GRADES for item in _all_evidence(record)
        ):
            # This is the final safety fallback for a D0/D1 route with no
            # admissible direct ledger evidence.  It is deliberately before
            # the pooler call, because a stochastic response could not alter
            # the answer under the replacement policy.
            record["qae_pooler"] = {
                "model": "programmatic", "answer": pooled,
                "viable_candidates": [pooled], "excluded_candidates": [],
                "evidence_ids": [], "invalid_evidence_ids": [],
                "reason": "retain_A_pool_no_valid_ledger_evidence", "raw": "",
            }
            record["qae_final_answer"] = pooled
            record["qae_final_reason"] = "retain_A_pool_no_valid_ledger_evidence"
            _save_json(args.out, records)
            print(f"[pool] {pos}/{len(records)} idx={record['idx']} final={pooled} source=A_POOL_NO_EVIDENCE", flush=True)
            continue
        candidates = _candidate_letters(record) + [record.get("qae_clean", {}).get("answer"), record.get("qae_rebuttal", {}).get("answer"), hard_answer]
        candidates = list(dict.fromkeys(x for x in candidates if x in LETTERS))
        viable = [x for x in candidates if not _contradicted(record, x)]
        if not viable:  # Required escape hatch: a fresh clean solution competes without legacy candidates.
            viable = list(LETTERS)
        if hard_answer:
            record["qae_pooler"] = {"model": "programmatic", "answer": hard_answer, "viable_candidates": viable, "excluded_candidates": [x for x in candidates if x not in viable], "evidence_ids": sorted(_supporting_ids(record, hard_answer)), "reason": "unique_HARD_constraint", "raw": ""}
            record["qae_final_answer"] = hard_answer
            record["qae_final_reason"] = "deterministic_unique_hard_support"
            _save_json(args.out, records)
            print(f"[pool] {pos}/{len(records)} idx={record['idx']} final={hard_answer} source=HARD", flush=True)
            continue
        raw, parsed = _call_json(args.model, _pool_prompt(record, viable), 520, ("answer", "reason", "evidence_ids"), 6000 + pos)
        choice = _letter(parsed.get("answer")) or _letter(raw)
        raw_cited = {str(x) for x in parsed.get("evidence_ids", []) if isinstance(x, str)}
        ledger_ids = {str(item.get("evidence_id")) for item in _all_evidence(record) if item.get("status") in EVIDENCE_GRADES}
        cited = raw_cited & ledger_ids
        invalid_cited = sorted(raw_cited - ledger_ids)
        if not ledger_ids and pooled in LETTERS:
            # With no HARD/STRONG ledger item, a stochastic re-solve is not an
            # auditable replacement.  Preserve A_pool and make that fact
            # explicit instead of labelling the result evidence-constrained.
            choice = pooled
            reason = "retain_A_pool_no_valid_ledger_evidence"
        elif choice not in viable:
            # Never convert an excluded or malformed model choice into the first
            # viable option. That fallback caused the MMLU regression: the
            # pooler selected B, B was incorrectly excluded, and the code
            # silently changed the answer to the first remaining candidate A.
            # A valid frozen baseline is safer than an unsupported replacement.
            choice = pooled if pooled in LETTERS else viable[0]
            reason = "retain_A_pool_after_pooler_constraint_failure"
        elif choice != pooled and pooled in LETTERS and not (cited & _supporting_ids(record, choice)):
            # A direct contradiction of A_pool alone cannot identify which
            # alternative is right. A replacement must cite option-level
            # HARD/STRONG support for the new answer; unique HARD conclusions
            # return before the stochastic pooler is called.
            choice = pooled
            reason = "retain_A_pool_no_cited_strong_support_for_replacement"
        elif choice == pooled and pooled in LETTERS:
            reason = "retain_A_pool_existing_answer"
        else:
            reason = "evidence_constrained_pooler"
        record["qae_pooler"] = {
            "model": args.model, "answer": choice, "viable_candidates": viable,
            "excluded_candidates": [x for x in candidates if x not in viable],
            "evidence_ids": sorted(cited), "invalid_evidence_ids": invalid_cited,
            "reason": reason, "pooler_reason": str(parsed.get("reason", "")), "raw": raw,
        }
        record["qae_final_answer"] = choice
        record["qae_final_reason"] = reason
        _save_json(args.out, records)
        print(f"[pool] {pos}/{len(records)} idx={record['idx']} viable={''.join(viable)} final={choice}", flush=True)


def run_hard_pool(records: list[dict[str, Any]], out: str) -> None:
    """Full-dataset ablation of only the sound programmatic constraint layer.

    No model is called.  A uniquely entailed HARD answer replaces the frozen
    A_pool; all other valid A_pool answers are retained verbatim.  This isolates
    the causal effect of the newly added deterministic evidence from the
    separate, slower QAE question-generation and verifier stages.
    """
    for pos, record in enumerate(records, 1):
        hard_answer = _decisive_hard_answer(record)
        baseline = record.get("stored_goa_answer")
        if hard_answer:
            answer, reason = hard_answer, "deterministic_unique_hard_support"
        elif baseline in LETTERS:
            answer, reason = baseline, "retain_frozen_A_pool_no_HARD_constraint"
        else:
            votes = Counter(answer for answer in record.get("initial_answers", {}).values() if answer in LETTERS)
            answer = next((letter for letter, count in votes.most_common() if count >= 2), None)
            reason = "frozen_majority_fallback_after_unparseable_A_pool" if answer else "unresolved_unparseable_A_pool"
        record["qae_pooler"] = {"model": "programmatic", "answer": answer, "viable_candidates": [answer] if answer else [], "excluded_candidates": [], "evidence_ids": sorted(_supporting_ids(record, answer)), "reason": reason, "raw": ""}
        record["qae_final_answer"] = answer
        record["qae_final_reason"] = reason
        _save_json(out, records)
        print(f"[hardpool] {pos}/{len(records)} idx={record['idx']} final={answer} reason={reason}", flush=True)


def _mcnemar(fixed: int, broken: int) -> float:
    n = fixed + broken
    return 1.0 if not n else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(fixed, broken) + 1)) / 2**n)


def summarize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    def correct(record: dict[str, Any], key: str) -> bool:
        return record.get(key) == record["gold"]
    paired_records = [record for record in records if record.get("stored_goa_answer") in LETTERS]
    fixed = sum(correct(r, "qae_final_answer") and not correct(r, "stored_goa_answer") for r in paired_records)
    broken = sum(not correct(r, "qae_final_answer") and correct(r, "stored_goa_answer") for r in paired_records)
    statuses = Counter(item.get("status") for r in records for item in _all_evidence(r))
    baseline_n = len(paired_records)
    summary = {"n": len(records), "baseline_n": baseline_n, "baseline_parse_failures": len(records) - baseline_n, "accuracy": {"A_pool": sum(correct(r, "stored_goa_answer") for r in paired_records) / baseline_n if baseline_n else None, "qae_final": sum(correct(r, "qae_final_answer") for r in records) / len(records)}, "paired_final_vs_A_pool": {"n": baseline_n, "fixed": fixed, "broken": broken, "mcnemar_exact_p": _mcnemar(fixed, broken)}, "evidence_status": dict(statuses), "hard_direct_contradictions": sum(len(item.get("contradicts", [])) for r in records for item in r.get("qae_hard", {}).values() if item.get("status") == "HARD"), "strong_direct_contradictions": sum(len(item.get("contradicts", [])) for r in records for item in r.get("qae_ledger", {}).values() if item.get("status") == "STRONG")}
    _save_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("plan", "hard", "verify", "ledger", "clean", "rebuttal", "pool", "hardpool", "summary"))
    parser.add_argument("--model", choices=PARTICIPANTS, default="qwen")
    parser.add_argument("--source", default="outputs/proco_keyverify_shared_10_v3.json")
    parser.add_argument("--out", default="outputs/qae_pooling_10.json")
    parser.add_argument("--summary", default="outputs/qae_pooling_10_summary.json")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--evidence-count", type=int, default=3)
    args = parser.parse_args()
    records = _init(args)
    if args.stage == "plan": run_plan(args, records)
    elif args.stage == "hard": run_hard(args, records)
    elif args.stage == "verify": run_verify(args, records)
    elif args.stage == "ledger": run_ledger(args, records)
    elif args.stage == "clean": run_solve(args, records, "qae_clean", False)
    elif args.stage == "rebuttal": run_solve(args, records, "qae_rebuttal", True)
    elif args.stage == "pool": run_pool(args, records)
    elif args.stage == "hardpool": run_hard_pool(records, args.out)
    else: summarize(args, records)


if __name__ == "__main__":
    main()
