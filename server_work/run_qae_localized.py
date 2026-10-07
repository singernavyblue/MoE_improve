#!/usr/bin/env python3
"""Conflict-localized QAE pooling, inspired by SwarmMind's role handoffs.

This is deliberately an ablation of ``run_qae_pooling.py`` rather than a
replacement.  It retains QAE's blind verification and conservative pooler, but
replaces generic option-driven question generation with a typed shared state:

  chains -> atomic claims -> one validated upstream disagreement -> blind check
  -> evidence-directness review -> existing safe pool.

The roles are functional prompts, not a vote.  No verifier sees an option
letter, the pooled answer, or another verifier's response.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import requests

from run_qae_pooling import (
    EVIDENCE_GRADES,
    LETTERS,
    PARTICIPANTS,
    _all_evidence,
    _call_json,
    _candidate_letters,
    _decisive_hard_answer,
    _full_json_value,
    _load,
    _save_json,
    _stem_options,
    _blind_answer_prompt,
    run_hard,
    run_ledger,
    run_pool,
    run_solve,
    run_verify,
    summarize,
)


CLAIM_TYPES = {"definition", "assumption", "formula", "substitution", "calculation", "comparison", "option_mapping"}
CONFLICT_TYPES = CLAIM_TYPES
ROUTES = {"numeric", "symbolic", "fact", "necessity", "counterexample"}
# These are routing labels, not a closed ontology for all future claims.  A
# diagnosis may put an unfamiliar but grounded category into ``new`` and
# preserve its label for later review instead of forcing it into a math-only
# claim schema.
PROBLEM_TYPES = {
    "numeric_calculation", "formula_derivation", "causal_mechanism",
    "conditional_logic", "fact_entity_relation", "open_ended",
}
DIAGNOSIS_TYPES = {
    "formula_or_calculation_error", "fact_or_concept_error",
    "condition_or_scope_mismatch", "entity_confusion",
    "evidence_insufficient", "no_verifiable_conflict",
}
CLAIM_CATEGORIES = {
    "quantitative_relation", "causal_mechanism", "conditional_constraint",
    "entity_relation", "new",
}
_VLLM_CHAT_ENDPOINT = "http://127.0.0.1:8000/v1/chat/completions"
_VLLM_SERVED_MODELS = {
    "qwen": "Qwen/Qwen2.5-7B-Instruct",
    "mathstral": "Mathstral-7B",
    "biomedical_llama": "BioMistral-7B",
}


def _trim(value: Any, limit: int = 1500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _controlled_choice(value: Any, allowed: set[str]) -> str:
    """Accept the first valid enum when a model echoes a ``a|b|c`` schema."""
    supplied = str(value or "").strip().lower()
    for part in supplied.split("|"):
        candidate = part.strip()
        if candidate in allowed:
            return candidate
    return supplied


def _source_has_disagreement(record: dict[str, Any]) -> bool:
    answers = {answer for answer in record.get("initial_answers", {}).values() if answer in LETTERS}
    return len(answers) >= 2


def _init(args: argparse.Namespace) -> list[dict[str, Any]]:
    if Path(args.out).exists():
        records = _load(args.out)
        # Outputs produced before the span-hybrid pipeline may legitimately be
        # resumed.  Additive defaults keep those artifacts readable without
        # re-running or silently replacing their legacy claim state.
        for record in records:
            record.setdefault("swarm_spans", {})
            record.setdefault("swarm_span_candidates", {})
            record.setdefault("swarm_diagnosis", {})
        return records
    source = _load(args.source)
    if args.only_disagreement:
        source = [item for item in source if _source_has_disagreement(item)]
    selected = source if args.limit <= 0 else source[:args.limit]
    records: list[dict[str, Any]] = []
    for raw in selected:
        item = dict(raw)
        item.update({
            "qae_plan": [], "qae_hard": {}, "qae_ledger": {},
            "qae_clean": {}, "qae_rebuttal": {}, "qae_pooler": {},
            "qae_final_answer": None, "qae_final_reason": "",
            "swarm_claims": {}, "swarm_normalization": {}, "swarm_conflict": {}, "swarm_guard": {},
            "swarm_spans": {}, "swarm_span_candidates": {}, "swarm_diagnosis": {},
        })
        records.append(item)
    _save_json(args.out, records)
    return records


def _claims_prompt(question: str, chains: dict[str, Any]) -> str:
    """Prompt a source-faithful, coverage-aware forensic claim extraction.

    The examples intentionally demonstrate (1) independent coverage of each
    frozen attempt, (2) atomic upstream claims rather than option conclusions,
    and (3) an empty result when an attempt supplies no checkable reasoning.
    They are compact adaptations of high-quality records in the existing audit
    ledger (MMLU buffer-overflow and MATH arithmetic traces).
    """
    attempts = "\n\n".join(
        f"M{slot} (its selected answer is intentionally hidden):\n{_trim(chain)}"
        for slot, chain in chains.items()
    )
    return f"""You are **Aster**, a meticulous forensic claim auditor working for a
skeptical replication committee. Your job is to build a source-faithful evidence
ledger, not to solve the problem. A later reviewer must be able to point from
every ledger entry back to one exact contiguous phrase in one frozen attempt.

## Mission and non-negotiable boundaries
- Extract only atomic, checkable statements explicitly made in the frozen
  attempts. Do not add domain knowledge, correct an attempt, rank attempts,
  infer an answer, or state which attempt is right.
- Process every supplied model label independently, in label order. If an
  attempt contains an eligible factual or inferential step, extract 1--3 useful
  claims from *that attempt*. Do not let M0's content substitute for M1 or M2.
  If an attempt contains only a conclusion, confidence statement, or vague
  rhetoric, emit no claim for it rather than inventing one.
- Prefer upstream material: definitions, explicit conditions, formulas,
  substitutions, calculations, and comparisons. Never extract an answer letter,
  an option label, a confidence score, or a bare conclusion such as "therefore
  option B is correct". `option_mapping` is not used in this task.

## Atomicity and provenance rules
- One claim = one proposition. Split "P and Q" only when P and Q can be checked
  separately; otherwise retain the smallest quote that supports the one claim.
- `quote` must be a short, exact, contiguous substring from the *same* model's
  attempt, ideally 5--30 words. It must be sufficient to justify `claim` by
  paraphrase alone. Do not merge two distant excerpts or strengthen/weaken what
  was said.
- Choose exactly one `type` from: definition, assumption, formula,
  substitution, calculation, comparison. Do not write a pipe-separated enum.
- IDs restart within each model: C1, C2, C3. `depends_on` may contain only IDs
  of earlier claims from the same model; use [] unless that logical dependency
  is explicit. Never place prose, a quote, or a cross-model ID in `depends_on`.
- Set `answer_impact` to high only if changing this statement could plausibly
  change the final answer; use medium for a useful intermediate step and low for
  background context.

## Few-shot examples

Example 1 — preserve source labels and extract upstream facts, not conclusions
Question: Buffer-overflow may remain as a bug if checks are incomplete.
Frozen attempts:
M0: Buffer overflow vulnerabilities occur when a program writes more data to a buffer than it can hold. This issue remains unaddressed if proper boundary checks are not implemented.
M1: Buffer overflow can happen if a program does not check whether data exceeds the boundaries of a designated buffer. If boundary checks are not done fully, buffer overflow bugs can remain in applications.
M2: Buffer-overflow occurs when a program attempts to write more data to a buffer than it can hold. Boundary checks ensure that data written to a buffer does not exceed its capacity.
Good JSON answer:
{{"claims":[{{"model":"M0","id":"C1","type":"definition","claim":"A buffer overflow occurs when a program writes more data to a buffer than it can hold.","quote":"Buffer overflow vulnerabilities occur when a program writes more data to a buffer than it can hold","depends_on":[],"answer_impact":"high"}},{{"model":"M0","id":"C2","type":"assumption","claim":"Missing proper boundary checks leaves the issue unaddressed.","quote":"This issue remains unaddressed if proper boundary checks are not implemented","depends_on":[],"answer_impact":"high"}},{{"model":"M1","id":"C1","type":"assumption","claim":"Incomplete boundary checks can leave buffer-overflow bugs in an application.","quote":"If boundary checks are not done fully, buffer overflow bugs can remain in applications","depends_on":[],"answer_impact":"high"}},{{"model":"M2","id":"C1","type":"comparison","claim":"Boundary checks keep data written to a buffer within its capacity.","quote":"Boundary checks ensure that data written to a buffer does not exceed its capacity","depends_on":[],"answer_impact":"high"}}]}}

Example 2 — retain calculation steps separately and preserve each source
Question: Evaluate (1+2i)6-3i.
Frozen attempts:
M0: Multiplying gives 1*6 + 2i*6 = 6 + 12i. Subtracting 3i gives 6 + 9i.
M1: First distribute 6 over 1+2i, obtaining 6+12i; then combine 12i-3i to obtain 9i.
M2: (6 + 12i) - 3i = 6 + (12-3)i = 6 + 9i.
Good JSON answer:
{{"claims":[{{"model":"M0","id":"C1","type":"calculation","claim":"Multiplying (1+2i) by 6 yields 6+12i.","quote":"1*6 + 2i*6 = 6 + 12i","depends_on":[],"answer_impact":"medium"}},{{"model":"M0","id":"C2","type":"calculation","claim":"Subtracting 3i from 6+12i yields 6+9i.","quote":"Subtracting 3i gives 6 + 9i","depends_on":["C1"],"answer_impact":"high"}},{{"model":"M1","id":"C1","type":"substitution","claim":"Distributing 6 over 1+2i gives 6+12i.","quote":"distribute 6 over 1+2i, obtaining 6+12i","depends_on":[],"answer_impact":"medium"}},{{"model":"M2","id":"C1","type":"calculation","claim":"(6+12i)-3i equals 6+9i.","quote":"(6 + 12i) - 3i = 6 + (12-3)i = 6 + 9i","depends_on":[],"answer_impact":"high"}}]}}

Example 3 — do not turn bare conclusions into pseudo-evidence
Question: Which statement is correct?
Frozen attempts:
M0: Therefore the answer is B.
M1: I choose C with high confidence.
M2: Option D is correct.
Good JSON answer:
{{"claims":[]}}

## Task
Question:
{question}

Frozen attempts:
{attempts}

Return exactly one valid JSON object, with no Markdown fences and no prose:
{{"claims":[{{"model":"M0","id":"C1","type":"definition","claim":"atomic paraphrase","quote":"exact contiguous source substring","depends_on":[],"answer_impact":"low"}}]}}"""


def run_claims(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_claims", {}).get("status") in {"DONE", "SKIPPED_HARD"}:
            continue
        if _decisive_hard_answer(record):
            record["swarm_claims"] = {"status": "SKIPPED_HARD", "claims": [], "raw": ""}
        else:
            chains = record.get("initial_responses", {})
            if args.independent_claims:
                # One model call per frozen attempt is deliberately more costly
                # than a joint call, but prevents the first/longest chain from
                # monopolising a small extractor's output budget.
                raw_by_model: dict[str, str] = {}
                merged_claims: list[Any] = []
                for offset, (slot, chain) in enumerate(chains.items()):
                    model_raw, model_parsed = _call_json(
                        args.model, _claims_prompt(record["question"], {slot: chain}),
                        520, ("claims",), 7100 + pos * 10 + offset,
                    )
                    raw_by_model[f"M{slot}"] = model_raw
                    values = model_parsed.get("claims", []) if isinstance(model_parsed.get("claims"), list) else []
                    merged_claims.extend(values)
                raw = json.dumps({"mode": "independent_per_model", "raw_by_model": raw_by_model}, ensure_ascii=False)
                parsed = {"claims": merged_claims}
            else:
                raw, parsed = _call_json(args.model, _claims_prompt(record["question"], chains), 950, ("claims",), 7100 + pos)
            # First validate source provenance, then assign runner-owned IDs in
            # a second pass.  Keeping these stages distinct prevents the model's
            # local IDs (for example C1) from becoming dangling dependencies
            # after another raw claim is rejected.
            accepted_raw: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            per_model: Counter[str] = Counter()
            source_ids_seen: set[tuple[str, str]] = set()
            raw_claims = parsed.get("claims", []) if isinstance(parsed.get("claims"), list) else []
            for raw_index, value in enumerate(raw_claims, 1):
                if not isinstance(value, dict):
                    rejected.append({"raw_index": raw_index, "rejection_reason": "claim_is_not_an_object"})
                    continue
                model = str(value.get("model", "")).upper().removeprefix("M")
                quote = str(value.get("quote", "")).strip()
                source_id = str(value.get("id", "")).strip().upper()
                claim = _trim(value.get("claim"), 360)
                supplied_type = str(value.get("type", "")).lower()
                # Small local models sometimes echo the schema's pipe-separated
                # enum verbatim.  Treat that specific formatting lapse as its
                # first concrete type, never as a new hybrid evidence class.
                claim_type = next((part for part in supplied_type.split("|") if part in CLAIM_TYPES), supplied_type)
                impact = str(value.get("answer_impact", "medium")).lower()
                base_audit = {"raw_index": raw_index, "model": f"M{model}" if model else "", "source_id": source_id, "claim": claim, "quote": quote[:300]}
                if model not in chains:
                    rejected.append({**base_audit, "rejection_reason": "unknown_source_model"})
                    continue
                if not claim:
                    rejected.append({**base_audit, "rejection_reason": "empty_claim"})
                    continue
                if not quote:
                    rejected.append({**base_audit, "rejection_reason": "empty_quote"})
                    continue
                if claim_type not in CLAIM_TYPES:
                    rejected.append({**base_audit, "rejection_reason": "invalid_claim_type"})
                    continue
                if impact not in {"low", "medium", "high"}:
                    rejected.append({**base_audit, "rejection_reason": "invalid_answer_impact"})
                    continue
                if source_id and not re.fullmatch(r"C[1-9][0-9]*", source_id):
                    rejected.append({**base_audit, "rejection_reason": "invalid_local_claim_id"})
                    continue
                if source_id and (model, source_id) in source_ids_seen:
                    rejected.append({**base_audit, "rejection_reason": "duplicate_local_claim_id"})
                    continue
                if per_model[model] >= 4:
                    rejected.append({**base_audit, "rejection_reason": "per_model_claim_limit"})
                    continue
                # The prompt renders chains with normalized whitespace.  Compare
                # against the same representation, while still requiring an
                # exact contiguous quote; otherwise valid multi-line excerpts
                # would be rejected merely because of a newline/space change.
                if _trim(quote, 10000) not in _trim(chains[model], 10000):
                    rejected.append({**base_audit, "rejection_reason": "quote_not_found_in_source_attempt"})
                    continue
                per_model[model] += 1
                if source_id:
                    source_ids_seen.add((model, source_id))
                dependencies_value = value.get("depends_on", [])
                raw_dependencies = (
                    [str(x).strip().upper() for x in dependencies_value if isinstance(x, str)]
                    if isinstance(dependencies_value, list)
                    else []
                )
                accepted_raw.append({
                    "model_slot": model, "source_id": source_id or f"C{per_model[model]}",
                    "type": claim_type, "claim": claim, "quote": quote[:300],
                    "raw_dependencies": raw_dependencies,
                    "answer_impact": impact,
                })

            # Map the source-local IDs to canonical, source-qualified IDs.
            # Later roles can now unambiguously cite M1-C2 rather than an
            # ambiguous C2 from some unknown attempt.
            source_to_canonical: dict[tuple[str, str], str] = {}
            canonical_position: dict[str, int] = {}
            claimed_per_model: Counter[str] = Counter()
            for item in accepted_raw:
                slot = item["model_slot"]
                claimed_per_model[slot] += 1
                canonical = f"M{slot}-C{claimed_per_model[slot]}"
                item["claim_id"] = canonical
                canonical_position[canonical] = claimed_per_model[slot]
                source_to_canonical[(slot, item["source_id"])] = canonical

            accepted: list[dict[str, Any]] = []
            for item in accepted_raw:
                canonical_dependencies: list[str] = []
                dependency_issues: list[dict[str, str]] = []
                for dependency in item["raw_dependencies"]:
                    # Only same-model, earlier local IDs are meaningful for an
                    # atomic reasoning trace.  Cross-model links would make a
                    # source chain look causally dependent on another model.
                    normalized = dependency.removeprefix(f"M{item['model_slot']}-")
                    mapped = source_to_canonical.get((item["model_slot"], normalized))
                    if not mapped:
                        dependency_issues.append({"dependency": dependency, "reason": "unknown_or_rejected_same_model_dependency"})
                    elif mapped == item["claim_id"] or canonical_position[mapped] >= canonical_position[item["claim_id"]]:
                        dependency_issues.append({"dependency": dependency, "reason": "dependency_must_reference_an_earlier_claim"})
                    else:
                        canonical_dependencies.append(mapped)
                if dependency_issues:
                    rejected.append({
                        "raw_index": None, "model": f"M{item['model_slot']}", "source_id": item["source_id"],
                        "claim": item["claim"], "quote": item["quote"],
                        "rejection_reason": "invalid_dependencies_removed", "dependency_issues": dependency_issues,
                    })
                accepted.append({
                    "claim_id": item["claim_id"], "model": f"M{item['model_slot']}", "source_id": item["source_id"],
                    "type": item["type"], "claim": item["claim"], "quote": item["quote"],
                    "depends_on": canonical_dependencies, "answer_impact": item["answer_impact"],
                })
            record["swarm_claims"] = {"status": "DONE", "claims": accepted, "rejected_claims": rejected, "raw": raw}
        _save_json(args.out, records)
        print(f"[claims] {pos}/{len(records)} idx={record['idx']} n={len(record['swarm_claims'].get('claims', []))}", flush=True)


# ---------------------------------------------------------------------------
# Span-first hybrid conflict pipeline
# ---------------------------------------------------------------------------
#
# The legacy claim stage asks a model to create both a proposition and its
# provenance quote.  The span-first path instead makes provenance a program
# property: every source response is segmented losslessly, and later model
# calls may only select program-owned span IDs.  Semantic structure is
# materialised only after a candidate pair has passed a conflict judgement.

_DIRECT_ANSWER_RE = re.compile(
    r"\b(?:the\s+)?(?:answer|option|choice)\s*(?:is|:|=)?\s*\(?[A-J]\)?\b",
    re.I,
)


def _trim_span_bounds(source: str, start: int, end: int) -> tuple[int, int]:
    """Trim only surrounding whitespace while preserving source offsets."""
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    return start, end


def _source_spans(model: str, source: Any) -> list[dict[str, Any]]:
    """Create a lossless, source-offset ledger for one frozen response.

    Splitting is intentionally deterministic and conservative.  A bad sentence
    boundary can make a span less convenient for retrieval, but it never loses
    source text or allows a generated quote to enter the evidence ledger.
    """
    text = str(source or "")
    if not text.strip():
        return []
    # Keep sentence punctuation in its preceding span; blank lines are useful
    # boundaries for enumerated derivations and display-math blocks.
    boundaries = list(re.finditer(r"\n+|(?<=[.!?])(?=\s)", text))
    windows: list[tuple[int, int]] = []
    cursor = 0
    for match in boundaries:
        end = match.end()
        start, end = _trim_span_bounds(text, cursor, end)
        if start < end:
            windows.append((start, end))
        cursor = end
    start, end = _trim_span_bounds(text, cursor, len(text))
    if start < end:
        windows.append((start, end))
    # A response containing no recognised boundary is still represented by one
    # exact span.  Conversely, an accidental zero-width regex boundary cannot
    # make text disappear because the tail is always appended above.
    spans: list[dict[str, Any]] = []
    for ordinal, (start, end) in enumerate(windows, 1):
        value = text[start:end]
        tokens = sorted(_content_tokens(value))
        spans.append({
            "span_id": f"{model}-S{ordinal}",
            "model": model,
            "start": start,
            "end": end,
            "text": value,
            "kind": "symbolic_or_formula" if _looks_symbolic(value) or re.search(r"\b(?:equation|formula|calculate|compute)\b", value, re.I) else "sentence",
            "content_tokens": tokens[:80],
            "is_direct_answer": bool(_DIRECT_ANSWER_RE.search(value)),
        })
    return spans


def run_spans(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    """Persist the complete raw-span ledger without any model generation."""
    for pos, record in enumerate(records, 1):
        if record.get("swarm_spans", {}).get("status") == "DONE":
            continue
        spans: list[dict[str, Any]] = []
        chains = record.get("initial_responses", {})
        for slot, chain in chains.items():
            spans.extend(_source_spans(f"M{slot}", chain))
        record["swarm_spans"] = {
            "status": "DONE",
            "segmentation": "deterministic_sentence_or_line_offsets_v1",
            "source_model_count": len(chains),
            "span_count": len(spans),
            "spans": spans,
        }
        _save_json(args.out, records)
        print(f"[spans] {pos}/{len(records)} idx={record['idx']} n={len(spans)}", flush=True)


def _span_numbers(text: str) -> set[str]:
    """Return copied numeric/symbolic anchors; this is retrieval-only data."""
    normalized = _normalized_text(text)
    values = set(re.findall(r"(?<![a-z])(?:\d+(?:\.\d+)?(?:e[+-]?\d+)?|10\s*\^\s*[+-]?\d+)(?![a-z])", normalized))
    values.update(re.findall(r"\\(?:[a-z]+)|[α-ω]", normalized))
    return values


def _span_is_retrievable(span: dict[str, Any]) -> bool:
    if span.get("is_direct_answer"):
        return False
    text = str(span.get("text", "")).strip()
    return len(text) >= 18 and len(_content_tokens(text)) >= 2


def _span_pair_score(left: dict[str, Any], right: dict[str, Any], document_frequency: Counter[str]) -> float:
    """High-recall lexical/symbolic ranking, never a contradiction verdict."""
    left_tokens = set(left.get("content_tokens") or _content_tokens(left.get("text", "")))
    right_tokens = set(right.get("content_tokens") or _content_tokens(right.get("text", "")))
    shared = left_tokens & right_tokens
    if not shared:
        return 0.0
    # Rarer shared terms are usually the entity/formula anchor.  This makes
    # generic reasoning words much less influential than, for example, HBr,
    # a compound name, ΔE, or a physical unit.
    rarity = sum(1.0 / max(1, document_frequency[token]) for token in shared)
    lexical = len(shared) / max(1.0, (len(left_tokens) * len(right_tokens)) ** 0.5)
    symbols = _span_numbers(left.get("text", "")) & _span_numbers(right.get("text", ""))
    symbolic_bonus = min(0.8, 0.2 * len(symbols))
    return lexical + rarity + symbolic_bonus


def _model_pair_key(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, str]:
    return tuple(sorted((str(left["model"]), str(right["model"]))))


def _span_candidate_pairs(spans: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Retrieve balanced cross-model span candidates without semantic claims.

    Exact lexical/symbolic overlap gives the localizer compact, high-recall
    evidence pairs.  If one source-model pair has no overlap, a small fallback
    of its most information-dense spans is retained and marked explicitly;
    the later judge may only reject it, never treat it as a conflict by itself.
    """
    usable = [span for span in spans if _span_is_retrievable(span)]
    model_names = sorted({str(span["model"]) for span in usable})
    if len(model_names) < 2:
        return []
    frequency: Counter[str] = Counter(
        token for span in usable for token in set(span.get("content_tokens") or [])
    )
    by_model: dict[str, list[dict[str, Any]]] = {
        model: [span for span in usable if span["model"] == model] for model in model_names
    }
    model_pairs = [(model_names[i], model_names[j]) for i in range(len(model_names)) for j in range(i + 1, len(model_names))]
    per_group = max(2, limit // max(1, len(model_pairs)))
    selected: list[dict[str, Any]] = []
    selected_refs: set[frozenset[str]] = set()

    def add(left: dict[str, Any], right: dict[str, Any], score: float, basis: str) -> None:
        refs = frozenset((str(left["span_id"]), str(right["span_id"])))
        if len(refs) != 2 or refs in selected_refs:
            return
        selected_refs.add(refs)
        selected.append({
            "span_refs": [str(left["span_id"]), str(right["span_id"])],
            "source_models": sorted((str(left["model"]), str(right["model"]))),
            "retrieval_score": round(score, 6),
            "retrieval_basis": basis,
        })

    for first, second in model_pairs:
        ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for left in by_model[first]:
            for right in by_model[second]:
                score = _span_pair_score(left, right, frequency)
                if score > 0:
                    ranked.append((score, left, right))
        ranked.sort(key=lambda value: (-value[0], value[1]["span_id"], value[2]["span_id"]))
        for score, left, right in ranked[:per_group]:
            add(left, right, score, "lexical_or_symbolic_span_overlap")
        # Retrieval cannot safely declare that an absent lexical match means
        # no semantic conflict.  Retain a bounded, auditable fallback rather
        # than manufacturing a negative conclusion.
        if not ranked:
            left_fallback = sorted(by_model[first], key=lambda span: (-len(span.get("content_tokens", [])), span["span_id"]))[:2]
            right_fallback = sorted(by_model[second], key=lambda span: (-len(span.get("content_tokens", [])), span["span_id"]))[:2]
            for left in left_fallback:
                for right in right_fallback:
                    add(left, right, 0.0, "fallback_information_dense_cross_model_pair")

    # First pass is balanced across every model pair; trim globally only after
    # that balance is established, preserving deterministic ordering.
    selected.sort(key=lambda pair: (-float(pair["retrieval_score"]), pair["span_refs"]))
    return selected[:max(1, limit)]


def run_span_candidates(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    """Create only answer-disagreement candidate pairs from the span ledger."""
    for pos, record in enumerate(records, 1):
        if record.get("swarm_span_candidates", {}).get("status"):
            continue
        span_state = record.get("swarm_spans", {})
        spans = span_state.get("spans", []) if span_state.get("status") == "DONE" else []
        if not _source_has_disagreement(record):
            state = {"status": "SKIPPED_NO_ANSWER_DISAGREEMENT", "candidate_pairs": []}
        elif not spans:
            state = {"status": "NO_SPANS", "candidate_pairs": []}
        else:
            pairs = _span_candidate_pairs(spans, args.span_candidate_limit)
            state = {
                "status": "DONE" if pairs else "NO_RETRIEVABLE_CROSS_MODEL_PAIR",
                "candidate_pairs": pairs,
                "span_count": len(spans),
                "candidate_limit": args.span_candidate_limit,
            }
        record["swarm_span_candidates"] = state
        _save_json(args.out, records)
        print(
            f"[span-candidates] {pos}/{len(records)} idx={record['idx']} "
            f"status={state['status']} pairs={len(state.get('candidate_pairs', []))}",
            flush=True,
        )


def _diagnosis_category(problem_type: str) -> str:
    """Choose a stable initial category when the model omits one.

    The category is an audit/routing hint only.  ``new`` remains available so
    an unfamiliar mechanism is recorded for later ontology review rather than
    being silently coerced into one of these initial buckets.
    """
    return {
        "numeric_calculation": "quantitative_relation",
        "formula_derivation": "quantitative_relation",
        "causal_mechanism": "causal_mechanism",
        "conditional_logic": "conditional_constraint",
        "fact_entity_relation": "entity_relation",
    }.get(problem_type, "new")


def _diagnosis_prompt(question: str, spans_by_id: dict[str, dict[str, Any]], pairs: list[dict[str, Any]]) -> str:
    """Ask for routing and error attribution before conflict localization.

    This role never sees option letters or frozen answers.  It may select only
    a program-retrieved span pair, which makes an affirmative diagnosis an
    auditable proposal rather than a free-form Claim extraction.
    """
    rendered: list[str] = []
    for number, pair in enumerate(pairs, 1):
        refs = [str(ref) for ref in pair.get("span_refs", [])]
        if len(refs) != 2 or any(ref not in spans_by_id for ref in refs):
            continue
        left, right = (spans_by_id[refs[0]], spans_by_id[refs[1]])
        rendered.append(
            f"Pair P{number} ({pair.get('retrieval_basis', 'retrieval')}):\n"
            f"{refs[0]} [{left['model']}]: {_span_snippet(left, 240)}\n"
            f"{refs[1]} [{right['model']}]: {_span_snippet(right, 240)}"
        )
    return f"""You are a conservative routing and difference-diagnosis reviewer.
Do not solve the multiple-choice problem, select an option, decide which source
is correct, or add facts.  Classify the reasoning shape, then decide whether
one displayed cross-model pair is a concrete, independently verifiable source
of disagreement worth sending to a conflict reviewer.

Use `verification_eligible: true` only if exactly one listed pair discusses a
specific factual, numerical, causal, entity, or condition/scope disagreement
that can be checked without options.  Different wording, compatible detail,
missing reasoning, or an open-ended task must be retained as A-pool and use
false.  If true, copy exactly the two displayed span IDs into `span_refs`.
`new_claim_label` is used only with claim_category `new`; it is a short
descriptive label, not a claim of truth.

Question:
{question}

Program-retrieved candidate pairs:
{chr(10).join(rendered) or 'None.'}

Return JSON only:
{{"problem_type":"numeric_calculation|formula_derivation|causal_mechanism|conditional_logic|fact_entity_relation|open_ended","diagnosis_type":"formula_or_calculation_error|fact_or_concept_error|condition_or_scope_mismatch|entity_confusion|evidence_insufficient|no_verifiable_conflict","verification_eligible":true,"span_refs":["M0-S1","M1-S2"],"claim_category":"quantitative_relation|causal_mechanism|conditional_constraint|entity_relation|new","new_claim_label":"none or short proposed category","reason":"brief source-grounded routing reason"}}"""


def _diagnosis_state(
    record: dict[str, Any], pairs: list[dict[str, Any]], parsed: dict[str, Any], raw: str,
) -> dict[str, Any]:
    """Validate a diagnostic proposal and make the A-pool fallback explicit."""
    problem_type = _controlled_choice(parsed.get("problem_type"), PROBLEM_TYPES)
    diagnosis_type = _controlled_choice(parsed.get("diagnosis_type"), DIAGNOSIS_TYPES)
    requested_refs = [str(ref) for ref in parsed.get("span_refs", []) if str(ref).strip()]
    allowed_pairs = {
        frozenset(str(ref) for ref in pair.get("span_refs", []))
        for pair in pairs if len(pair.get("span_refs", [])) == 2
    }
    category = _controlled_choice(parsed.get("claim_category"), CLAIM_CATEGORIES)
    if category not in CLAIM_CATEGORIES:
        category = _diagnosis_category(problem_type) if problem_type in PROBLEM_TYPES else "new"
    new_label = _canonical_field(parsed.get("new_claim_label"))
    if category != "new":
        new_label = "none"
    elif new_label == "none":
        new_label = "unclassified"
    base = {
        "diagnosis_id": "D0",
        "problem_type": problem_type or "unknown",
        "diagnosis_type": diagnosis_type or "unknown",
        "claim_category": category,
        "new_claim_label": new_label,
        "span_refs": requested_refs,
        "reason": _trim(parsed.get("reason"), 500),
        "raw": raw,
        "candidate_pair_count_seen": len(pairs),
    }
    eligible = _truthy_json(parsed.get("verification_eligible"))
    if problem_type not in PROBLEM_TYPES:
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "invalid_problem_type"}
    if diagnosis_type not in DIAGNOSIS_TYPES:
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "invalid_diagnosis_type"}
    if problem_type == "open_ended":
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "open_ended_problem"}
    if diagnosis_type in {"evidence_insufficient", "no_verifiable_conflict"}:
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "diagnosis_not_verifiable"}
    if not eligible:
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "diagnosis_did_not_authorize_verification"}
    if len(requested_refs) != 2 or frozenset(requested_refs) not in allowed_pairs:
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "diagnosis_pair_not_program_retrieved"}
    spans_by_id = {
        str(span.get("span_id")): span
        for span in record.get("swarm_spans", {}).get("spans", [])
    }
    source_models = {str(spans_by_id.get(ref, {}).get("model", "")) for ref in requested_refs}
    if len(source_models) != 2 or any(ref not in spans_by_id for ref in requested_refs):
        return {**base, "status": "RETAIN_A_POOL", "route": "retain_a_pool", "rejection_reason": "diagnosis_pair_not_cross_model"}
    return {
        **base,
        "status": "ELIGIBLE",
        "route": "span_first_verify",
        "source_models": sorted(source_models),
    }


def run_diagnose(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    """Classify reasoning shape and admit at most one auditable pair per item."""
    for pos, record in enumerate(records, 1):
        if record.get("swarm_diagnosis", {}).get("status"):
            continue
        if _decisive_hard_answer(record):
            state = {"status": "SKIPPED_HARD", "route": "hard_constraint", "reason": "program-owned hard constraint"}
        else:
            spans_by_id = {
                str(span.get("span_id")): span
                for span in record.get("swarm_spans", {}).get("spans", [])
            }
            pair_state = record.get("swarm_span_candidates", {})
            all_pairs = pair_state.get("candidate_pairs", []) if pair_state.get("status") == "DONE" else []
            # Keep the classifier context below the vLLM context limit.  The
            # selected pair is then the *only* pair offered to the localizer.
            shown_pairs = all_pairs[:12]
            if not shown_pairs:
                state = {
                    "status": "RETAIN_A_POOL", "route": "retain_a_pool",
                    "reason": "no program-retrieved cross-model span pair",
                    "rejection_reason": "no_span_candidate_pair",
                    "candidate_pair_count_seen": 0,
                }
            else:
                raw, parsed = _call_json(
                    args.model, _diagnosis_prompt(record["question"], spans_by_id, shown_pairs),
                    460, ("problem_type", "diagnosis_type", "verification_eligible"), 7400 + pos,
                )
                state = _diagnosis_state(record, shown_pairs, parsed, raw)
        record["swarm_diagnosis"] = state
        _save_json(args.out, records)
        print(
            f"[diagnose] {pos}/{len(records)} idx={record['idx']} "
            f"status={state['status']} type={state.get('problem_type', 'n/a')}",
            flush=True,
        )


def _span_snippet(span: dict[str, Any], limit: int = 300) -> str:
    """Render a display-only prefix; stored offsets always retain full text."""
    return _trim(span.get("text", ""), limit)


def _span_localize_prompt(
    question: str, spans_by_id: dict[str, dict[str, Any]], pairs: list[dict[str, Any]],
    diagnosis: dict[str, Any] | None = None,
) -> str:
    rendered: list[str] = []
    for number, pair in enumerate(pairs, 1):
        refs = [str(ref) for ref in pair.get("span_refs", [])]
        if len(refs) != 2 or refs[0] not in spans_by_id or refs[1] not in spans_by_id:
            continue
        left, right = (spans_by_id[refs[0]], spans_by_id[refs[1]])
        rendered.append(
            f"Pair P{number} ({pair.get('retrieval_basis', 'retrieval')}; score={pair.get('retrieval_score', 0)}):\n"
            f"{refs[0]} [{left['model']}]: {_span_snippet(left)}\n"
            f"{refs[1]} [{right['model']}]: {_span_snippet(right)}"
        )
    problem_type = str((diagnosis or {}).get("problem_type", "unknown"))
    category = str((diagnosis or {}).get("claim_category", "unknown"))
    route_hint = {
        "numeric_calculation": "Compare the exact numerical quantities, units, and calculation result.",
        "formula_derivation": "Compare the formula applicability, algebraic relation, or derivation condition.",
        "causal_mechanism": "Compare the stated mechanism or causal direction under the stated conditions.",
        "conditional_logic": "Compare the condition, scope, necessity, or exception before comparing conclusions.",
        "fact_entity_relation": "Compare the entity identity, property, or relation explicitly asserted by the spans.",
    }.get(problem_type, "Use only the exact entity, attribute, and conditions supported by the spans.")
    return f"""You are a conservative cross-chain contradiction reviewer.  The source
spans below are immutable evidence: do not quote text not present in them, do
not solve the multiple-choice question, and do not choose an answer option.

Upstream routing (an audit hint, not evidence): problem_type={problem_type};
claim_category={category}. {route_hint}

For one listed pair only, return CONFLICT only when both spans discuss the same
entity and attribute under compatible stated conditions and their propositions
cannot both be true.  Different scope, missing detail, uncertainty, alternative
methods, a bare answer, or merely different wording is COMPATIBLE or
UNDECIDABLE, not a conflict.  Retrieval score is not evidence.

If and only if there is a real conflict, use the exact two span IDs from that
listed pair; give compact entity/attribute/conditions and the two directions
using only words/formulas supported by the spans.  For `left_entity_span`,
`right_entity_span`, `left_attribute_span`, and `right_attribute_span`, copy a
non-empty exact contiguous substring from the respective displayed span that
supports the named field.  Do not use pronouns such as "it" or "they" as an
entity.  If `conditions` is not `none`, also copy
`left_condition_span` and `right_condition_span` from both spans; do not call
conditions shared when one span does not state them.  Then write one standalone blind verification question that settles
precisely that factual disagreement.
It must not name models, spans, options, or answer letters.

Question:
{question}

Candidate pairs:
{chr(10).join(rendered) or 'None.'}

Return JSON only:
{{"status":"CONFLICT|COMPATIBLE|UNDECIDABLE","span_refs":["M0-S1","M1-S2"],"same_entity":true,"same_conditions":true,"entity":"canonical entity","attribute":"canonical attribute","conditions":"stated condition or none","left_entity_span":"exact left substring","right_entity_span":"exact right substring","left_attribute_span":"exact left substring","right_attribute_span":"exact right substring","left_condition_span":"exact left substring or none","right_condition_span":"exact right substring or none","left_direction":"increase|decrease|unchanged|present|absent|other","right_direction":"increase|decrease|unchanged|present|absent|other","conflict_type":"definition|assumption|formula|substitution|calculation|comparison","description":"incompatible propositions","why_decisive":"why resolving it can alter the result","target_question":"standalone factual or calculation question","verification_route":"numeric|symbolic|fact|necessity|counterexample"}}"""


def _truthy_json(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


_SPAN_ROUTE_ALIASES = {
    "calculation": "numeric",
    "formula": "symbolic",
    "definition": "fact",
    "comparison": "fact",
}


def _span_route(value: Any) -> str:
    """Map controlled route synonyms without accepting arbitrary free text."""
    supplied = str(value or "").lower().strip()
    for part in supplied.split("|"):
        route = _SPAN_ROUTE_ALIASES.get(part, part)
        if route in ROUTES:
            return route
    return supplied


def _span_field_repair_prompt(
    question: str, left: dict[str, Any], right: dict[str, Any],
) -> str:
    """Repair only grounding fields for an already selected potential pair."""
    return f"""You are repairing structured evidence fields, not deciding whether
two propositions conflict.  Keep every field tied to the two immutable source
spans below.  Return compact entity, attribute, and conditions plus exact
contiguous supporting substrings from EACH corresponding span.  If a condition
is not explicitly present in both, return conditions and both condition spans
as `none`.  Do not use pronouns as entity.  Choose verification_route exactly
from numeric, symbolic, fact, necessity, counterexample.

Question:
{question}

Left source span:
{_span_snippet(left, 520)}

Right source span:
{_span_snippet(right, 520)}

Return JSON only:
{{"entity":"canonical entity","attribute":"canonical attribute","conditions":"stated condition or none","left_entity_span":"exact left substring","right_entity_span":"exact right substring","left_attribute_span":"exact left substring","right_attribute_span":"exact right substring","left_condition_span":"exact left substring or none","right_condition_span":"exact right substring or none","verification_route":"numeric|symbolic|fact|necessity|counterexample"}}"""


def _span_ref_render(record: dict[str, Any], refs: list[str]) -> str:
    """Render either span-first or legacy claim evidence for downstream guard."""
    spans = {
        str(span.get("span_id")): span
        for span in record.get("swarm_spans", {}).get("spans", [])
    }
    if refs and all(ref in spans for ref in refs):
        return "\n".join(
            f"{ref}: {spans[ref].get('text', '')}"
            for ref in refs
        )
    claims = {item["claim_id"]: item for item in record.get("swarm_claims", {}).get("claims", [])}
    return "\n".join(
        f"{ref}: {claims.get(ref, {}).get('claim', '')} | quote: {claims.get(ref, {}).get('quote', '')}"
        for ref in refs
    )


def _call_vllm_chat_json(
    model_key: str, prompt: str, tokens: int, required: tuple[str, ...], seed: int,
) -> tuple[str, dict[str, Any]]:
    """Call vLLM's chat endpoint without the legacy completion-only adapter.

    Recent vLLM serves completion requests for Qwen but exposes Mathstral and
    BioMistral only through /v1/chat/completions. This narrow adapter is used
    for blind verification only; it preserves the verifier's no-options,
    no-chain context and never turns an HTTP failure into evidence.
    """
    best_raw, best = "", {}
    for retry in range(2):
        try:
            response = requests.post(
                _VLLM_CHAT_ENDPOINT,
                json={
                    "model": _VLLM_SERVED_MODELS.get(model_key, model_key),
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": tokens,
                    "temperature": 0.25,
                    "seed": seed + retry,
                },
                timeout=300,
            )
            response.raise_for_status()
            payload = response.json()
            raw = str(payload["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError, ValueError, requests.RequestException):
            raw = ""
        value = _full_json_value(raw)
        parsed = {"questions": value} if isinstance(value, list) else (value or {})
        if len(raw) > len(best_raw):
            best_raw, best = raw, parsed
        if all(str(parsed.get(key, "")).strip() for key in required):
            return raw, parsed
    return best_raw, best


def run_span_verify(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    """Blind evidence verification using the endpoint that each vLLM model serves."""
    for pos, record in enumerate(records, 1):
        stem, _ = _stem_options(record["question"])
        for evidence in record.get("qae_plan", []):
            answers = evidence.setdefault("answers", {})
            if answers.get(args.model, {}).get("answer"):
                continue
            raw, parsed = _call_vllm_chat_json(
                args.model, _blind_answer_prompt(stem, evidence), 280, ("answer",), 2000 + pos,
            )
            answer = str(parsed.get("answer", "")).strip()
            answers[args.model] = {
                "answer": answer or "UNKNOWN",
                "reason": str(parsed.get("reason", "")),
                "raw": raw,
            }
            _save_json(args.out, records)
            print(
                f"[span-verify {args.model}] {pos}/{len(records)} idx={record['idx']} "
                f"{evidence['evidence_id']}={answer[:48] or 'PARSE_FAIL'}",
                flush=True,
            )


def run_span_localize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    """Judge candidate span pairs and materialise claims only for real conflicts."""
    for pos, record in enumerate(records, 1):
        if record.get("swarm_conflict", {}).get("status"):
            continue
        if _decisive_hard_answer(record):
            record["swarm_conflict"] = {"status": "SKIPPED_HARD"}
            record["qae_plan"] = []
        else:
            diagnosis = record.get("swarm_diagnosis", {})
            if args.diagnosis_gate and diagnosis.get("status") != "ELIGIBLE":
                record["swarm_conflict"] = {
                    "status": "SKIPPED_DIAGNOSIS",
                    "span_refs": [],
                    "diagnosis_id": diagnosis.get("diagnosis_id", "D0"),
                    "diagnosis_status": diagnosis.get("status", "MISSING"),
                    "rejection_reason": diagnosis.get("rejection_reason", "diagnosis_gate_requires_eligible_pair"),
                }
                record["qae_plan"] = []
                _save_json(args.out, records)
                print(f"[span-localize] {pos}/{len(records)} idx={record['idx']} status=SKIPPED_DIAGNOSIS", flush=True)
                continue
            spans_by_id = {
                str(span.get("span_id")): span
                for span in record.get("swarm_spans", {}).get("spans", [])
            }
            pair_state = record.get("swarm_span_candidates", {})
            pairs = pair_state.get("candidate_pairs", []) if pair_state.get("status") == "DONE" else []
            if args.diagnosis_gate:
                selected_refs = frozenset(str(ref) for ref in diagnosis.get("span_refs", []))
                pairs = [pair for pair in pairs if frozenset(str(ref) for ref in pair.get("span_refs", [])) == selected_refs]
            allowed_pairs = {
                frozenset(str(ref) for ref in pair.get("span_refs", []))
                for pair in pairs
                if len(pair.get("span_refs", [])) == 2
            }
            if not pairs:
                record["swarm_conflict"] = {
                    "status": "NO_SPAN_CANDIDATE_PAIR",
                    "span_refs": [],
                    "rejection_reason": pair_state.get("status", "span_candidates_not_run"),
                }
                record["qae_plan"] = []
            else:
                raw, parsed = _call_json(
                    args.model, _span_localize_prompt(
                        record["question"], spans_by_id, pairs,
                        diagnosis if args.diagnosis_gate else None,
                    ),
                    700, ("status",), 7600 + pos,
                )
                refs = [str(ref) for ref in parsed.get("span_refs", []) if str(ref) in spans_by_id]
                status = str(parsed.get("status", "UNDECIDABLE")).upper()
                source_models = {str(spans_by_id[ref].get("model", "")) for ref in refs}
                span_texts = [str(spans_by_id[ref].get("text", "")) for ref in refs]

                def structured_fields(value: dict[str, Any]) -> dict[str, Any]:
                    entity = _canonical_field(value.get("entity"))
                    attribute = _canonical_field(value.get("attribute"))
                    conditions = _canonical_field(value.get("conditions"))
                    entity_anchors = [_trim(value.get("left_entity_span"), 300), _trim(value.get("right_entity_span"), 300)]
                    attribute_anchors = [_trim(value.get("left_attribute_span"), 300), _trim(value.get("right_attribute_span"), 300)]
                    condition_anchors = [_trim(value.get("left_condition_span"), 300), _trim(value.get("right_condition_span"), 300)]
                    entity_grounded = (
                        len(span_texts) == 2
                        and all(_quote_contains_span(text, anchor) for text, anchor in zip(span_texts, entity_anchors))
                        and all(_field_matches_span(entity, anchor) for anchor in entity_anchors)
                    )
                    attribute_grounded = (
                        len(span_texts) == 2
                        and all(_quote_contains_span(text, anchor) for text, anchor in zip(span_texts, attribute_anchors))
                        and all(_field_matches_span(attribute, anchor) for anchor in attribute_anchors)
                    )
                    conditions_grounded = conditions == "none" or (
                        len(span_texts) == 2
                        and all(_quote_contains_span(text, anchor) for text, anchor in zip(span_texts, condition_anchors))
                        and all(_field_matches_span(conditions, anchor) for anchor in condition_anchors)
                    )
                    return {
                        "entity": entity, "attribute": attribute, "conditions": conditions,
                        "entity_anchors": entity_anchors, "attribute_anchors": attribute_anchors,
                        "condition_anchors": condition_anchors, "entity_grounded": entity_grounded,
                        "attribute_grounded": attribute_grounded, "conditions_grounded": conditions_grounded,
                        "entity_resolved": _subject_is_resolved(entity),
                        "left_direction": _canonical_direction(value.get("left_direction")),
                        "right_direction": _canonical_direction(value.get("right_direction")),
                    }

                fields = structured_fields(parsed)
                # A valid cross-model conflict proposal with opposite stated
                # directions may get one focused chance to repair omitted span
                # anchors.  This never repairs a same-model pair, a changed
                # pair, a shared-direction "conflict", or ungrounded entity.
                raw_left_direction = _normalized_text(parsed.get("left_direction")).strip()
                raw_right_direction = _normalized_text(parsed.get("right_direction")).strip()
                recovery_eligible = (
                    status == "CONFLICT"
                    and len(refs) == 2
                    and frozenset(refs) in allowed_pairs
                    and len(source_models) == 2
                    and _truthy_json(parsed.get("same_entity"))
                    and _truthy_json(parsed.get("same_conditions"))
                    and fields["entity"] not in {"none", "unknown"}
                    and (not args.coreference_gate or fields["entity_resolved"])
                    and fields["entity_grounded"]
                    and _span_directions_incompatible(
                        fields["left_direction"], fields["right_direction"],
                        raw_left_direction, raw_right_direction,
                    )
                    and (not fields["attribute_grounded"] or not fields["conditions_grounded"])
                )
                if recovery_eligible:
                    repair_raw, repair = _call_json(
                        args.model,
                        _span_field_repair_prompt(record["question"], spans_by_id[refs[0]], spans_by_id[refs[1]]),
                        430,
                        ("entity", "attribute", "conditions", "left_entity_span", "right_entity_span", "left_attribute_span", "right_attribute_span", "left_condition_span", "right_condition_span", "verification_route"),
                        8600 + pos,
                    )
                    if repair:
                        parsed = {**parsed, **repair}
                        raw = json.dumps({"conflict_judgement": raw, "field_repair": repair_raw}, ensure_ascii=False)
                        fields = structured_fields(parsed)
                entity = fields["entity"]
                attribute = fields["attribute"]
                conditions = fields["conditions"]
                entity_anchors = fields["entity_anchors"]
                attribute_anchors = fields["attribute_anchors"]
                condition_anchors = fields["condition_anchors"]
                left_direction = fields["left_direction"]
                right_direction = fields["right_direction"]
                field_grounded = fields["entity_grounded"] and fields["attribute_grounded"] and fields["conditions_grounded"]
                supplied_ctype = str(parsed.get("conflict_type", "")).lower()
                ctype = next((part for part in supplied_ctype.split("|") if part in CONFLICT_TYPES), supplied_ctype)
                route = _span_route(parsed.get("verification_route"))
                target = str(parsed.get("target_question", "")).strip()
                valid = (
                    status == "CONFLICT"
                    and len(refs) == 2
                    and frozenset(refs) in allowed_pairs
                    and len(source_models) == 2
                    and _truthy_json(parsed.get("same_entity"))
                    and _truthy_json(parsed.get("same_conditions"))
                    and entity not in {"none", "unknown"}
                    and attribute not in {"none", "unknown"}
                    and (not args.coreference_gate or fields["entity_resolved"])
                    and left_direction != "unknown"
                    and right_direction != "unknown"
                    and _span_directions_incompatible(
                        left_direction, right_direction,
                        raw_left_direction, raw_right_direction,
                    )
                    and field_grounded
                    and ctype in CONFLICT_TYPES
                    and route in ROUTES
                    and _valid_target(target)
                )
                if valid:
                    structured_claims = []
                    for ref, direction in zip(refs, (left_direction, right_direction)):
                        span = spans_by_id[ref]
                        structured_claims.append({
                            "span_ref": ref,
                            "model": span["model"],
                            "start": span["start"],
                            "end": span["end"],
                            "quote": span["text"],
                            "entity": entity,
                            "attribute": attribute,
                            "conditions": conditions,
                            "direction": direction,
                            "entity_span": entity_anchors[0 if ref == refs[0] else 1],
                            "attribute_span": attribute_anchors[0 if ref == refs[0] else 1],
                            "condition_span": condition_anchors[0 if ref == refs[0] else 1],
                        })
                    record["swarm_conflict"] = {
                        "status": "CONFLICT", "conflict_id": "D1", "span_refs": refs,
                        "claim_refs": refs, "conflict_type": ctype, "description": _trim(parsed.get("description"), 500),
                        "why_decisive": _trim(parsed.get("why_decisive"), 450), "target_question": target,
                        "verification_route": route, "source_models": sorted(source_models),
                        "diagnosis_id": diagnosis.get("diagnosis_id", "D0") if args.diagnosis_gate else None,
                        "problem_type": diagnosis.get("problem_type", "unknown") if args.diagnosis_gate else "unknown",
                        "diagnosis_type": diagnosis.get("diagnosis_type", "unknown") if args.diagnosis_gate else "unknown",
                        "claim_category": diagnosis.get("claim_category", "unknown") if args.diagnosis_gate else "unknown",
                        "claim_category_version": "diagnostic-routing-v1" if args.diagnosis_gate else None,
                        "new_claim_label": diagnosis.get("new_claim_label", "none") if args.diagnosis_gate else "none",
                        "structured_claims": structured_claims, "raw": raw,
                    }
                    record["qae_plan"] = [{
                        "evidence_id": "D1-E1", "type": route, "question": target,
                        "why": f"Span-localized {ctype} conflict D1 over {', '.join(refs)}",
                        "origin": "span_hybrid_localized_conflict", "conflict_id": "D1", "claim_refs": refs,
                        "diagnosis_id": diagnosis.get("diagnosis_id", "D0") if args.diagnosis_gate else None,
                        "answers": {}, "status": "PENDING",
                    }]
                else:
                    record["swarm_conflict"] = {
                        "status": "NO_VALID_SPAN_CONFLICT", "raw": raw, "span_refs": refs,
                        "rejected_status": status, "source_models": sorted(source_models),
                        "rejection_reason": "requires_a_retrieved_cross_model_pair_with_grounded_shared_fields",
                    }
                    record["qae_plan"] = []
        _save_json(args.out, records)
        print(f"[span-localize] {pos}/{len(records)} idx={record['idx']} status={record['swarm_conflict']['status']}", flush=True)


NORMAL_POLARITIES = {"affirm", "negate", "numeric", "comparative", "unknown"}


def _canonical_field(value: Any, fallback: str = "none") -> str:
    """Normalize a normalizer field into a deterministic comparison key."""
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", text)[:120] or fallback


def _normalize_prompt(question: str, claims: list[dict[str, Any]]) -> str:
    rendered = "\n".join(
        f"{item['claim_id']} ({item['model']}, {item['type']}): {item['claim']}\n"
        f"quote: {item['quote']}"
        for item in claims
    )
    return f"""You are Nia, a conservative semantic indexer for an evidence audit.
You do not solve the question and do not decide whether a claim is true. For
each supplied claim, create a compact comparison representation using only its
claim and quote. The purpose is to help a program find possible cross-model
disagreements, not to declare one.

Use short lower-case canonical phrases. Put "none" in conditions when no
condition is stated. `subject` is the entity or quantity discussed;
`predicate` is the one attribute/relation being asserted; `value` is the
asserted value/outcome. Use exactly one polarity: affirm, negate, numeric,
comparative, or unknown. Keep every claim_id exactly unchanged. Do not merge,
drop, rewrite, or add claims.

Example:
Input claim: M0-C1: Formula P is applicable when temperature is below 0 C.
Output item: {{"claim_id":"M0-C1","subject":"formula p","predicate":"applicability","conditions":"temperature below 0 c","value":"applicable","polarity":"affirm"}}

Question:
{question}

Claims:
{rendered or 'No claims.'}

Return JSON only:
{{"normalized":[{{"claim_id":"M0-C1","subject":"canonical entity","predicate":"canonical attribute","conditions":"none","value":"asserted value","polarity":"affirm"}}]}}"""


_AMBIGUOUS_SUBJECTS = {
    "a", "an", "the", "it", "its", "they", "them", "their", "theirs",
    "this", "that", "these", "those", "one", "ones", "something", "anything",
}
_FIELD_STOPWORDS = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "is", "are", "be", "as"}
_DIRECTION_PATTERNS = {
    "increase": r"\b(?:increase|increases|increased|increasing|higher|rise|rises|rose|rising|gain|gains|gained)\b",
    "decrease": r"\b(?:decrease|decreases|decreased|decreasing|lower|drop|drops|dropped|fall|falls|fell|reduc(?:e|es|ed|ing))\b",
    "unchanged": r"\b(?:unchanged|same|identical|constant|preserved)\b|\b(?:no|does not)\s+change\b|\bremains?\s+the\s+same\b",
    "present": r"\b(?:present|appears?|exists?|forms?|observed)\b",
    "absent": r"\b(?:absent|disappears?|lacks?|missing|not present)\b",
}


def _normalized_text(value: Any) -> str:
    """Normalize Unicode without throwing away formula or Greek-symbol content."""
    return unicodedata.normalize("NFKC", str(value or "")).casefold()


def _formula_fingerprint(value: Any) -> str:
    """Compare a copied formula/symbol span modulo case and whitespace only."""
    return re.sub(r"\s+", "", _normalized_text(value).replace("\\", ""))


def _looks_symbolic(value: Any) -> bool:
    text = str(value or "")
    return bool(re.search(r"[<>=|^_+*/]|[α-ωΑ-Ω]", text))


def _content_tokens(value: str) -> set[str]:
    """Content words, formulas, chemistry and Greek symbols for grounding checks."""
    raw = unicodedata.normalize("NFKC", str(value or ""))
    normalized = raw.casefold()
    tokens: set[str] = set()
    for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE):
        if token in _FIELD_STOPWORDS:
            continue
        stem = token
        for suffix in ("ing", "edly", "ed", "es", "s"):
            if len(stem) > len(suffix) + 3 and stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        tokens.add(stem)
    # In symbolic expressions, single-character variables (including ``A``)
    # and Greek symbols are evidence, not natural-language stop words.
    if _looks_symbolic(raw):
        for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE):
            tokens.add(token)
    for direction, pattern in _DIRECTION_PATTERNS.items():
        if re.search(pattern, normalized):
            tokens.add(direction)
    return tokens


def _subject_is_resolved(subject: str) -> bool:
    """Reject standalone pronouns/articles that cannot identify a D1 entity."""
    return subject.strip().lower() not in _AMBIGUOUS_SUBJECTS


def _field_matches_span(field: str, span: str) -> bool:
    """A field must be lexically/formulaically supported by its exact span."""
    if _looks_symbolic(field) and _looks_symbolic(span) and _formula_fingerprint(field) == _formula_fingerprint(span):
        return True
    field_text, span_text = _normalized_text(field), _normalized_text(span)
    hbr_pattern = r"\bhbr\b|\bhydrogen\s+bromide\b"
    if re.search(hbr_pattern, field_text) and re.search(hbr_pattern, span_text):
        return True
    field_tokens, span_tokens = _content_tokens(field), _content_tokens(span)
    return bool(field_tokens and span_tokens and field_tokens & span_tokens)


def _canonical_direction(value: Any) -> str:
    text = _normalized_text(value)
    if text in {"", "none", "unknown"}:
        return "unknown"
    for direction in ("increase", "decrease", "unchanged", "present", "absent"):
        if re.search(_DIRECTION_PATTERNS[direction], text):
            return direction
    return "other"


_OTHER_DIRECTION_OPPOSITES = {
    "continuous": "discontinuous",
    "discontinuous": "continuous",
    "active": "inactive",
    "inactive": "active",
    "possible": "impossible",
    "impossible": "possible",
    "stable": "unstable",
    "unstable": "stable",
    "direct": "indirect",
    "indirect": "direct",
}


def _span_directions_incompatible(
    left: str, right: str, left_raw: str = "", right_raw: str = "",
) -> bool:
    """Admit only a controlled, evidence-bearing directional contradiction.

    The model's `status: CONFLICT` is a proposal, not evidence.  In particular,
    two `increase` claims with different wording are compatible and must not
    create a locator call.  `other` keeps a small explicit opposite lexicon for
    qualitative pairs such as continuous/discontinuous; arbitrary different
    words are deliberately not treated as contradictory.
    """
    if {left, right} in ({"increase", "decrease"}, {"present", "absent"}):
        return True
    if "unchanged" in {left, right} and ({left, right} & {"increase", "decrease"}):
        return True
    if left != "other" or right != "other":
        return False
    raw = (_normalized_text(left_raw), _normalized_text(right_raw))
    if not all(raw) or raw[0] == raw[1]:
        return False
    for first, second in _OTHER_DIRECTION_OPPOSITES.items():
        if re.search(rf"\b{re.escape(first)}\b", raw[0]) and re.search(rf"\b{re.escape(second)}\b", raw[1]):
            return True
    # Treat an explicit "not X" versus X as a contradiction, but avoid making
    # all lexical differences into claims of conflict.
    return bool(
        re.fullmatch(r"not\s+(.+)", raw[0]) and raw[0][4:] == raw[1]
        or re.fullmatch(r"not\s+(.+)", raw[1]) and raw[1][4:] == raw[0]
    )


def _comparison_slots(parsed: dict[str, Any], fields: dict[str, str]) -> dict[str, str]:
    """Provide stable entity/attribute/direction slots without losing legacy fields."""
    entity = _canonical_field(parsed.get("entity"))
    attribute = _canonical_field(parsed.get("attribute"))
    direction = _canonical_direction(parsed.get("direction"))
    if entity in {"none", "unknown"}:
        entity = fields["subject"]
    if attribute in {"none", "unknown"}:
        attribute = fields["predicate"]
    if direction == "unknown":
        direction = _canonical_direction(fields["value"])
    return {"entity": entity, "attribute": attribute, "direction": direction}


def _single_normalize_prompt(
    question: str, claim: dict[str, Any], recovery_reason: str = "", grounded: bool = False,
    field_span_gate: bool = True,
) -> str:
    """Normalize exactly one program-owned claim."""
    recovery = (
        f"\nThe preceding attempt was invalid because: {recovery_reason}. Return every required field this time.\n"
        if recovery_reason else ""
    )
    span_consistency_rule = """
Each field must reuse at least one meaningful word, controlled synonym, or copied
formula/symbol from its own span; do not use a span for a different relation.""" if field_span_gate else ""
    grounding_rules = """
For subject, predicate, and value, also return `subject_span`, `predicate_span`,
and `value_span`: each must be a non-empty, exact contiguous substring copied
from the Exact source quote and must directly support that field. Do not use a
span merely because it is nearby. If no exact supporting span exists, use
`unknown` for that field and for its span.""" + span_consistency_rule if grounded else ""
    schema = (
        '{"subject":"canonical entity or unknown","predicate":"canonical relation or unknown",'
        '"conditions":"none or stated condition","value":"asserted value or unknown",'
        '"polarity":"affirm","subject_span":"exact source substring or unknown",'
        '"predicate_span":"exact source substring or unknown","value_span":"exact source substring or unknown",'
        '"entity":"canonical target of comparison","attribute":"canonical compared property",'
        '"direction":"increase|decrease|unchanged|present|absent|other"}'
        if grounded else
        '{"subject":"canonical entity or unknown","predicate":"canonical relation or unknown",'
        '"conditions":"none or stated condition","value":"asserted value or unknown","polarity":"affirm",'
        '"entity":"canonical target of comparison","attribute":"canonical compared property",'
        '"direction":"increase|decrease|unchanged|present|absent|other"}'
    )
    return f"""You are Nia, a conservative semantic indexer for an evidence audit.
This task concerns exactly ONE atomic claim. Do not solve the multiple-choice question,
judge truth, choose an option, mention a model, or add facts not in the claim and quote.
Convert the claim into compact lower-case comparison fields. `subject` is the entity or
quantity, `predicate` is the asserted attribute/relation, `conditions` is the stated
condition (`none` if absent), and `value` is the asserted outcome. Use one polarity:
affirm, negate, numeric, comparative, or unknown. If a field cannot be grounded in the
supplied text, write `unknown` rather than guessing.

Also return comparison slots: `entity` is the canonical target, `attribute` is the
single property being compared, and `direction` is one of increase, decrease,
unchanged, present, absent, or other. Keep these slots stable across paraphrases.
For example, "the endpoint value remains unchanged" has entity "e particle energy
spectrum", attribute "endpoint energy", direction "unchanged"; "the endpoint
decreases" uses the same entity and attribute with direction "decrease".
Do not put endpoint direction in a different slot merely because the wording differs.
{grounding_rules}{recovery}
Question:
{question}

Claim type: {claim['type']}
Claim: {claim['claim']}
Exact source quote: {claim['quote']}

Return exactly one JSON object with no Markdown or extra keys:
{schema}"""


def _quote_contains_span(quote: str, span: Any) -> bool:
    """Require a non-empty contiguous provenance span, ignoring only whitespace."""
    cleaned_span = _trim(span, 300)
    return bool(cleaned_span and cleaned_span.lower() not in {"unknown", "none"} and cleaned_span.lower() in _trim(quote, 10_000).lower())


def _strict_normalization_item(
    parsed: dict[str, Any], quote: str, grounded: bool, coreference_gate: bool = True,
    field_span_gate: bool = True,
) -> tuple[dict[str, str] | None, str]:
    """Validate one model response without allowing an omitted claim to vanish."""
    polarity = str(parsed.get("polarity", "")).lower().strip()
    if polarity not in NORMAL_POLARITIES:
        return None, "invalid_polarity"
    fields = {
        "subject": _canonical_field(parsed.get("subject")),
        "predicate": _canonical_field(parsed.get("predicate")),
        "conditions": _canonical_field(parsed.get("conditions")),
        "value": _canonical_field(parsed.get("value")),
        "polarity": polarity,
    }
    unresolved = [name for name in ("subject", "predicate", "value") if fields[name] in {"none", "unknown"}]
    if unresolved:
        return None, f"unresolved_{'_'.join(unresolved)}"
    if coreference_gate and not _subject_is_resolved(fields["subject"]):
        return None, "ambiguous_subject_coreference"
    rendered = " ".join(fields.values())
    if re.search(r"\b(?:option|choice)\s*[A-J]\b|\banswer\s+letter\b|\bmodel\s+M?\d+\b", rendered, re.I):
        return None, "contains_forbidden_workflow_reference"
    if grounded:
        spans = {
            "subject_span": _trim(parsed.get("subject_span"), 300),
            "predicate_span": _trim(parsed.get("predicate_span"), 300),
            "value_span": _trim(parsed.get("value_span"), 300),
        }
        invalid_spans = [name for name, span in spans.items() if not _quote_contains_span(quote, span)]
        if invalid_spans:
            return None, f"ungrounded_{'_'.join(invalid_spans)}"
        if field_span_gate:
            mismatched_fields = [
                field for field in ("subject", "predicate", "value")
                if not _field_matches_span(fields[field], spans[f"{field}_span"])
            ]
            if mismatched_fields:
                return None, f"field_span_mismatch_{'_'.join(mismatched_fields)}"
        fields.update(spans)
    fields.update(_comparison_slots(parsed, fields))
    return fields, ""


def _strict_normalize_claim(args: argparse.Namespace, question: str, claim: dict[str, Any], seed: int) -> dict[str, Any]:
    """Return one row for every input claim, with at most one targeted recovery."""
    attempts: list[dict[str, Any]] = []
    failure_reason = ""
    for pass_number in (1, 2):
        prompt = _single_normalize_prompt(
            question, claim, failure_reason, args.grounded_normalization, args.field_span_gate,
        )
        required = ("subject", "predicate", "value", "polarity", "entity", "attribute", "direction")
        if args.grounded_normalization:
            required += ("subject_span", "predicate_span", "value_span")
        raw, parsed = _call_json(args.model, prompt, 360 if args.grounded_normalization else 260, required, seed + pass_number * 10)
        fields, failure_reason = _strict_normalization_item(
            parsed, claim["quote"], args.grounded_normalization,
            args.coreference_gate, args.field_span_gate,
        )
        attempts.append({"pass": pass_number, "raw": raw, "validation": "NORMALIZED" if fields else failure_reason})
        if fields:
            return {"claim_id": claim["claim_id"], **fields, "status": "NORMALIZED", "attempts": attempts}
    return {
        "claim_id": claim["claim_id"], "subject": "unknown", "predicate": "unknown",
        "conditions": "none", "value": "unknown", "polarity": "unknown",
        "entity": "unknown", "attribute": "unknown", "direction": "unknown",
        "status": "UNRESOLVED", "failure_reason": failure_reason or "invalid_normalizer_output",
        "attempts": attempts,
    }


def _comparison_tokens(value: str) -> set[str]:
    return _content_tokens(value)


def _value_comparison_tokens(value: str, hbr_dedup: bool = True) -> set[str]:
    """Expand a small, explicit chemistry alias set before containment checks."""
    tokens = _comparison_tokens(value)
    if hbr_dedup and ("hbr" in tokens or {"hydrogen", "bromide"} <= tokens):
        tokens.update({"hbr", "hydrogen", "bromide"})
    return tokens


def _values_equivalent_or_entailing(
    left: dict[str, Any], right: dict[str, Any], hbr_dedup: bool = True,
) -> bool:
    """Suppress same-polarity value refinements, never opposite-polarity claims."""
    if left["polarity"] != right["polarity"]:
        return False
    if left["value"] == right["value"]:
        return True
    left_tokens = _value_comparison_tokens(left["value"], hbr_dedup)
    right_tokens = _value_comparison_tokens(right["value"], hbr_dedup)
    return bool(left_tokens and right_tokens and (left_tokens <= right_tokens or right_tokens <= left_tokens))


def _field_compatible(left: str, right: str) -> bool:
    """High-recall retrieval check; the localizer remains the conflict judge."""
    if left == right:
        return True
    left_tokens, right_tokens = _comparison_tokens(left), _comparison_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    return bool(shared) and (left_tokens <= right_tokens or right_tokens <= left_tokens or len(shared) / min(len(left_tokens), len(right_tokens)) >= 0.75)


def _condition_compatibility(left: str, right: str) -> str | None:
    if left == right:
        return "exact_conditions"
    if left == "none" or right == "none":
        return "condition_unspecified_on_one_side"
    return "overlapping_conditions" if _field_compatible(left, right) else None


def _normalized_candidate_pairs(
    items: list[dict[str, Any]], claims_by_id: dict[str, dict[str, Any]], compatible: bool = False,
    hbr_dedup: bool = True,
) -> list[dict[str, Any]]:
    """Generate program-owned *possible* D1 pairs, never verdicts.

    Equality of the normalized entity/attribute/condition key is only a
    retrieval criterion. The localizer still decides whether values are truly
    incompatible, preventing compatible detail from becoming a false conflict.
    """
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(items):
        for right in items[left_index + 1:]:
            if claims_by_id[left["claim_id"]]["model"] == claims_by_id[right["claim_id"]]["model"]:
                continue
            entity_left = left.get("entity", left["subject"])
            entity_right = right.get("entity", right["subject"])
            attribute_left = left.get("attribute", left["predicate"])
            attribute_right = right.get("attribute", right["predicate"])
            direction_left = left.get("direction", _canonical_direction(left["value"]))
            direction_right = right.get("direction", _canonical_direction(right["value"]))
            key_left = (entity_left, attribute_left, left["conditions"])
            key_right = (entity_right, attribute_right, right["conditions"])
            # Identical assertions are agreement, not a useful disagreement
            # candidate. Different values or polarities merit a semantic check.
            if _values_equivalent_or_entailing(left, right, hbr_dedup):
                continue
            # A shared directional claim such as "increase" is a refinement,
            # not a contradiction.  ``other`` intentionally falls through so
            # non-ordered factual claims can still be audited.
            if direction_left == direction_right and direction_left != "other":
                continue
            if key_left == key_right:
                basis = "exact_entity_attribute_conditions"
            elif compatible and _field_compatible(entity_left, entity_right) and _field_compatible(attribute_left, attribute_right):
                condition_basis = _condition_compatibility(left["conditions"], right["conditions"])
                if not condition_basis:
                    continue
                basis = f"compatible_entity_attribute_{condition_basis}"
            else:
                continue
            pairs.append({
                "claim_refs": [left["claim_id"], right["claim_id"]],
                "comparison_key": list(key_left), "right_comparison_key": list(key_right),
                "left_assertion": {"direction": direction_left, "value": left["value"]},
                "right_assertion": {"direction": direction_right, "value": right["value"]},
                "retrieval_basis": basis,
            })
    return pairs


def run_normalize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_normalization", {}).get("status"):
            continue
        claims = record.get("swarm_claims", {}).get("claims", [])
        claims_by_id = {item["claim_id"]: item for item in claims}
        if not claims:
            record["swarm_normalization"] = {
                "status": "NO_CLAIMS", "normalized": [], "rows": [], "candidate_pairs": [], "raw": "",
                "coverage": {"expected": 0, "observed": 0, "normalized": 0, "unresolved": 0, "complete": True},
            }
        elif args.strict_normalization:
            rows = [
                _strict_normalize_claim(args, record["question"], claim, 7150 + pos * 100 + claim_pos)
                for claim_pos, claim in enumerate(claims, 1)
            ]
            expected_ids = set(claims_by_id)
            observed_ids = [str(row.get("claim_id", "")) for row in rows]
            duplicate_ids = sorted({claim_id for claim_id in observed_ids if observed_ids.count(claim_id) > 1})
            missing_ids = sorted(expected_ids - set(observed_ids))
            unexpected_ids = sorted(set(observed_ids) - expected_ids)
            normalized = [row for row in rows if row.get("status") == "NORMALIZED"]
            unresolved = [row for row in rows if row.get("status") != "NORMALIZED"]
            coverage_complete = (
                len(rows) == len(expected_ids)
                and not missing_ids
                and not unexpected_ids
                and not duplicate_ids
            )
            semantic_coverage_complete = coverage_complete and not unresolved
            # A partial but audited record cannot support a negative conclusion
            # ("no D1 exists"), yet a fully grounded pair inside it may still be
            # safely sent to the localizer for a positive conflict check.
            pairs = _normalized_candidate_pairs(
                normalized, claims_by_id, compatible=args.compatible_d1, hbr_dedup=args.hbr_dedup,
            ) if coverage_complete else []
            record["swarm_normalization"] = {
                "status": "COMPLETE" if semantic_coverage_complete else "PARTIAL_NORMALIZATION" if coverage_complete else "BLOCKED_NORMALIZATION",
                "rows": rows, "normalized": normalized, "unresolved_claim_ids": [row["claim_id"] for row in unresolved],
                "candidate_pairs": pairs,
                "coverage": {
                    "expected": len(expected_ids), "observed": len(rows), "normalized": len(normalized),
                    "unresolved": len(unresolved), "missing_ids": missing_ids,
                    "unexpected_ids": unexpected_ids, "duplicate_ids": duplicate_ids,
                    "complete": coverage_complete, "semantic_complete": semantic_coverage_complete,
                },
            }
        else:
            raw, parsed = _call_json(args.model, _normalize_prompt(record["question"], claims), 1050, ("normalized",), 7150 + pos)
            normalized: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for value in parsed.get("normalized", []) if isinstance(parsed.get("normalized"), list) else []:
                if not isinstance(value, dict):
                    continue
                claim_id = str(value.get("claim_id", ""))
                polarity = str(value.get("polarity", "unknown")).lower()
                if claim_id not in claims_by_id or claim_id in seen_ids or polarity not in NORMAL_POLARITIES:
                    continue
                subject = _canonical_field(value.get("subject"))
                predicate = _canonical_field(value.get("predicate"))
                value_text = _canonical_field(value.get("value"))
                # A missing subject/predicate would create broad, meaningless
                # pairings, so do not promote it to the comparison index.
                if subject == "none" or predicate == "none":
                    continue
                fields = {
                    "claim_id": claim_id, "subject": subject, "predicate": predicate,
                    "conditions": _canonical_field(value.get("conditions")),
                    "value": value_text, "polarity": polarity,
                }
                fields.update(_comparison_slots(value, fields))
                normalized.append(fields)
                seen_ids.add(claim_id)
            pairs = _normalized_candidate_pairs(normalized, claims_by_id, hbr_dedup=args.hbr_dedup)
            record["swarm_normalization"] = {
                "status": "DONE", "normalized": normalized, "candidate_pairs": pairs,
                "unindexed_claim_ids": sorted(set(claims_by_id) - seen_ids), "raw": raw,
            }
        _save_json(args.out, records)
        state = record["swarm_normalization"]
        coverage = state.get("coverage", {})
        print(
            f"[normalize] {pos}/{len(records)} idx={record['idx']} status={state.get('status')} "
            f"indexed={len(state.get('normalized', []))} unresolved={coverage.get('unresolved', 0)} "
            f"pairs={len(state.get('candidate_pairs', []))}",
            flush=True,
        )


def _normalized_localize_prompt(question: str, claims_by_id: dict[str, dict[str, Any]], pairs: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for number, pair in enumerate(pairs, 1):
        left, right = (claims_by_id[claim_id] for claim_id in pair["claim_refs"])
        key = " | ".join(pair["comparison_key"])
        right_key = " | ".join(pair.get("right_comparison_key", pair["comparison_key"]))
        left_assertion = pair.get("left_assertion", {})
        right_assertion = pair.get("right_assertion", {})
        rendered.append(
            f"Pair P{number}; retrieval basis: {pair.get('retrieval_basis', 'exact_subject_predicate_conditions')}\n"
            f"Left comparison slots (entity | attribute | conditions): {key}; "
            f"direction={left_assertion.get('direction', 'other')}; value={left_assertion.get('value', '')}\n"
            f"Right comparison slots (entity | attribute | conditions): {right_key}; "
            f"direction={right_assertion.get('direction', 'other')}; value={right_assertion.get('value', '')}\n"
            f"{left['claim_id']} ({left['model']}): {left['claim']} | quote: {left['quote']}\n"
            f"{right['claim_id']} ({right['model']}): {right['claim']} | quote: {right['quote']}"
        )
    return f"""You are the conflict facilitator in an evidence-audit workflow.
Each listed pair was retrieved because its entity and attribute are exact or
compatible; conditions may be identical, overlapping, or unspecified on one
side. Decide whether ONE pair contains a real factual incompatibility under a
shared interpretation. Different scope, compatible detail, uncertainty, or
alternative wording is NOT a conflict. Do not decide which claim is true,
choose an answer option, or mention model labels in the verification question.

If a genuine conflict exists, prefer the earliest, most upstream pair that can
change the answer. Write one standalone factual/calculation check that resolves
exactly the disagreement. If no listed pair is genuinely incompatible, return
NO_CONFLICT.

Question:
{question}

Program-generated candidate pairs:
{chr(10).join(rendered) or 'None.'}

Return JSON only:
{{"status":"CONFLICT|NO_CONFLICT|UNSUITABLE","conflict_id":"D1","claim_refs":["M0-C1","M1-C1"],"conflict_type":"definition|assumption|formula|substitution|calculation|comparison","description":"the incompatible propositions","why_decisive":"why resolving it can alter the result","target_question":"standalone factual or calculation question","verification_route":"numeric|symbolic|fact|necessity|counterexample"}}"""


def _localize_prompt(question: str, answers: dict[str, Any], claims: list[dict[str, Any]]) -> str:
    claim_text = "\n".join(f"{claim['claim_id']} [{claim['type']}, impact={claim['answer_impact']}]: {claim['claim']} | quote: {claim['quote']}" for claim in claims)
    attempts = ", ".join(f"M{slot}={answer}" for slot, answer in answers.items() if answer in LETTERS)
    return f"""You are the Critic/Facilitator.  Localize ONE earliest, upstream,
answer-relevant factual disagreement among the typed claims below.  Two claims
are a disagreement only when they make incompatible statements under the same
conditions.  Different wording, missing detail, or compatible steps are NOT a
conflict.  Do not decide which final answer option is correct.

Question:
{question}

Frozen attempts chose different letters: {attempts}
Typed claim state:
{claim_text or 'No usable claims.'}

If a genuine conflict exists, it MUST cite claims from at least TWO DIFFERENT
model labels (for example M0 and M1). Two claims from the same attempt cannot
form D1. Create one standalone check that resolves exactly that point. It must
not mention models, chains, candidates, options, or answer letters. Prefer
numeric/symbolic checks when applicable. If no such direct check can be written,
return NO_CONFLICT rather than a vague question.

Return JSON only:
{{"status":"CONFLICT|NO_CONFLICT|UNSUITABLE","conflict_id":"D1","claim_refs":["M0-C1","M1-C2"],"conflict_type":"definition|assumption|formula|substitution|calculation|comparison|option_mapping","description":"the incompatible propositions","why_decisive":"why resolving it can alter the result","target_question":"standalone factual or calculation question","verification_route":"numeric|symbolic|fact|necessity|counterexample"}}"""


def _valid_target(question: str) -> bool:
    banned = r"\b(option|choice|candidate|answer letter|model\s*M?\d|chain|attempt)\b"
    return bool(question.strip()) and len(question) >= 12 and not re.search(banned, question, re.I)


def _referenced_models(claims_by_id: dict[str, dict[str, Any]], refs: list[str]) -> set[str]:
    """Return the frozen-attempt labels behind a proposed conflict.

    A localized disagreement is an inter-model object.  This code check prevents
    sequential statements from one attempt being promoted to D1.
    """
    return {str(claims_by_id[ref].get("model", "")) for ref in refs if ref in claims_by_id}


def run_localize(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_conflict", {}).get("status"):
            continue
        if _decisive_hard_answer(record):
            record["swarm_conflict"] = {"status": "SKIPPED_HARD"}
            record["qae_plan"] = []
        else:
            claims = record.get("swarm_claims", {}).get("claims", [])
            claims_by_id = {claim["claim_id"]: claim for claim in claims}
            normalized_state = record.get("swarm_normalization", {})
            if args.strict_normalization and normalized_state.get("status") == "BLOCKED_NORMALIZATION":
                record["swarm_conflict"] = {
                    "status": "BLOCKED_NORMALIZATION", "claim_refs": [], "source_models": [],
                    "rejection_reason": "strict_normalization_has_unresolved_claims",
                    "unresolved_claim_ids": normalized_state.get("unresolved_claim_ids", []),
                }
                record["qae_plan"] = []
                _save_json(args.out, records)
                print(f"[localize] {pos}/{len(records)} idx={record['idx']} status=BLOCKED_NORMALIZATION", flush=True)
                continue
            candidate_pairs = normalized_state.get("candidate_pairs", []) if args.normalized_d1 else []
            allowed_pair_refs = {frozenset(str(ref) for ref in pair.get("claim_refs", [])) for pair in candidate_pairs}
            if args.normalized_d1 and not candidate_pairs:
                partial = normalized_state.get("status") == "PARTIAL_NORMALIZATION"
                record["swarm_conflict"] = {
                    "status": "INCONCLUSIVE_NORMALIZATION" if partial else "NO_NORMALIZED_CANDIDATE_PAIR",
                    "claim_refs": [], "source_models": [],
                    "rejection_reason": "partial_audited_normalization_produced_no_candidate"
                    if partial else "no_cross_model_same_key_different_value_pair",
                    "unresolved_claim_ids": normalized_state.get("unresolved_claim_ids", []) if partial else [],
                }
                record["qae_plan"] = []
                _save_json(args.out, records)
                print(f"[localize] {pos}/{len(records)} idx={record['idx']} status={record['swarm_conflict']['status']}", flush=True)
                continue
            prompt = (
                _normalized_localize_prompt(record["question"], claims_by_id, candidate_pairs)
                if args.normalized_d1
                else _localize_prompt(record["question"], record.get("initial_answers", {}), claims)
            )
            raw, parsed = _call_json(args.model, prompt, 620, ("status",), 7200 + pos)
            refs = [str(x) for x in parsed.get("claim_refs", []) if str(x) in claims_by_id]
            source_models = _referenced_models(claims_by_id, refs)
            status = str(parsed.get("status", "UNSUITABLE")).upper()
            target = str(parsed.get("target_question", "")).strip()
            supplied_ctype = str(parsed.get("conflict_type", "")).lower()
            supplied_route = str(parsed.get("verification_route", "")).lower()
            ctype = next((part for part in supplied_ctype.split("|") if part in CONFLICT_TYPES), supplied_ctype)
            route = next((part for part in supplied_route.split("|") if part in ROUTES), supplied_route)
            valid = (
                status == "CONFLICT"
                and len(refs) >= 2
                and len(source_models) >= 2
                and ctype in CONFLICT_TYPES
                and route in ROUTES
                and _valid_target(target)
                and (not args.normalized_d1 or (len(refs) == 2 and frozenset(refs) in allowed_pair_refs))
            )
            if valid:
                record["swarm_conflict"] = {
                    "status": "CONFLICT", "conflict_id": "D1", "claim_refs": refs[:3], "conflict_type": ctype,
                    "description": _trim(parsed.get("description"), 500), "why_decisive": _trim(parsed.get("why_decisive"), 450),
                    "target_question": target, "verification_route": route,
                    "source_models": sorted(source_models), "raw": raw,
                }
                record["qae_plan"] = [{
                    "evidence_id": "D1-E1", "type": route, "question": target,
                    "why": f"Localized {ctype} conflict D1 over {', '.join(refs[:3])}",
                    "origin": "swarm_localized_conflict", "conflict_id": "D1", "claim_refs": refs[:3],
                    "answers": {}, "status": "PENDING",
                }]
            else:
                record["swarm_conflict"] = {
                    "status": "NO_VALID_LOCALIZED_CONFLICT", "raw": raw,
                    "rejected_status": status, "claim_refs": refs,
                    "source_models": sorted(source_models),
                    "rejection_reason": "requires_two_distinct_source_models"
                    if status == "CONFLICT" and len(refs) >= 2 and len(source_models) < 2
                    else "claim_refs_not_a_program_generated_normalized_pair"
                    if status == "CONFLICT" and args.normalized_d1 and frozenset(refs) not in allowed_pair_refs
                    else "invalid_localized_conflict",
                }
                record["qae_plan"] = []
        _save_json(args.out, records)
        print(f"[localize] {pos}/{len(records)} idx={record['idx']} status={record['swarm_conflict']['status']}", flush=True)


def _guard_prompt(record: dict[str, Any], evidence: dict[str, Any]) -> str:
    conflict = record.get("swarm_conflict", {})
    relevant = _span_ref_render(record, [str(ref) for ref in conflict.get("claim_refs", [])])
    answers = "\n".join(f"{key}: {value.get('answer', 'UNKNOWN')}" for key, value in evidence.get("answers", {}).items())
    return f"""You are the Evidence-Directness Reviewer.  Decide only whether the
blind evidence directly resolves the localized conflict; do not choose a final
multiple-choice answer or use option letters.  DIRECT means the settled factual
answer distinguishes the incompatible referenced claims under their stated
conditions.  INDIRECT is relevant but leaves the claimed disagreement open.
UNRELATED is not about the disagreement.  Admit evidence only if DIRECT.

Localized conflict: {conflict.get('description', '')}
Referenced claims:
{relevant}
Verification question: {evidence.get('question', '')}
Blind answers:
{answers}
Settled answer: {evidence.get('normalized_answer', 'UNKNOWN')}

Return JSON only:
{{"decision":"ADMIT|REJECT","directness":"DIRECT|INDIRECT|UNRELATED","reason":"short explanation"}}"""


def run_guard(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    for pos, record in enumerate(records, 1):
        if record.get("swarm_guard", {}).get("status"):
            continue
        evidence = record.get("qae_ledger", {}).get("D1-E1")
        if not evidence or evidence.get("status") != "STRONG" or record.get("swarm_conflict", {}).get("status") != "CONFLICT":
            record["swarm_guard"] = {"status": "NOT_ELIGIBLE", "reason": "requires localized conflict plus STRONG blind evidence"}
        else:
            raw, parsed = _call_json(args.model, _guard_prompt(record, evidence), 300, ("decision", "directness"), 7300 + pos)
            directness = str(parsed.get("directness", "UNRELATED")).upper()
            decision = str(parsed.get("decision", "REJECT")).upper()
            admitted = decision == "ADMIT" and directness == "DIRECT"
            record["swarm_guard"] = {"status": "ADMITTED" if admitted else "REJECTED", "decision": decision, "directness": directness, "reason": _trim(parsed.get("reason"), 450), "raw": raw}
            if not admitted:
                # Preserve the raw ledger for audit, but remove its authority to
                # contradict/support an option or authorize an answer replacement.
                evidence["supports"] = []
                evidence["contradicts"] = []
                evidence["mapping_reason"] = str(evidence.get("mapping_reason", "")) + " | blocked_by_directness_guard"
        _save_json(args.out, records)
        print(f"[guard] {pos}/{len(records)} idx={record['idx']} {record['swarm_guard']['status']}", flush=True)


def _localized_summary(args: argparse.Namespace, records: list[dict[str, Any]]) -> None:
    summarize(args, records)
    summary = _load(args.summary)
    conflict_status = Counter(item.get("swarm_conflict", {}).get("status") for item in records)
    guards = Counter(item.get("swarm_guard", {}).get("status") for item in records)
    routes = Counter(item.get("swarm_conflict", {}).get("verification_route") for item in records if item.get("swarm_conflict", {}).get("status") == "CONFLICT")
    claims = [claim for item in records for claim in item.get("swarm_claims", {}).get("claims", [])]
    normalized = [item for record in records for item in record.get("swarm_normalization", {}).get("normalized", [])]
    candidate_pairs = [pair for record in records for pair in record.get("swarm_normalization", {}).get("candidate_pairs", [])]
    normalization_rows = [row for record in records for row in record.get("swarm_normalization", {}).get("rows", [])]
    unresolved_rows = [row for row in normalization_rows if row.get("status") == "UNRESOLVED"]
    coverage_complete_records = sum(
        bool(record.get("swarm_normalization", {}).get("coverage", {}).get("complete"))
        for record in records
        if record.get("swarm_normalization", {}).get("status") != "NO_CLAIMS"
    )
    blocked_normalization_records = sum(
        record.get("swarm_normalization", {}).get("status") == "BLOCKED_NORMALIZATION"
        for record in records
    )
    partial_normalization_records = sum(
        record.get("swarm_normalization", {}).get("status") == "PARTIAL_NORMALIZATION"
        for record in records
    )
    diagnosis_states = Counter(record.get("swarm_diagnosis", {}).get("status", "MISSING") for record in records)
    diagnosis_problem_types = Counter(
        record.get("swarm_diagnosis", {}).get("problem_type", "unknown")
        for record in records if record.get("swarm_diagnosis", {}).get("status") == "ELIGIBLE"
    )
    diagnosis_error_types = Counter(
        record.get("swarm_diagnosis", {}).get("diagnosis_type", "unknown")
        for record in records if record.get("swarm_diagnosis", {}).get("status") == "ELIGIBLE"
    )
    new_claim_labels = Counter(
        record.get("swarm_diagnosis", {}).get("new_claim_label", "")
        for record in records
        if record.get("swarm_diagnosis", {}).get("status") == "ELIGIBLE"
        and record.get("swarm_diagnosis", {}).get("claim_category") == "new"
    )
    admitted = {item.get("idx") for item in records if item.get("swarm_guard", {}).get("status") == "ADMITTED"}
    changed = [item for item in records if item.get("qae_final_answer") != item.get("stored_goa_answer")]
    summary["conflict_localization"] = {
        "selection": "frozen records with at least two distinct parseable initial answers" if args.only_disagreement else "source order",
        "claim_count": len(claims), "mean_claims_per_record": len(claims) / len(records) if records else 0,
        "conflict_status": dict(conflict_status), "verification_routes": dict(routes), "directness_guard": dict(guards),
        "admitted_record_indices": sorted(admitted),
        "changed_answers": len(changed),
        "changed_with_admitted_direct_evidence": sum(item.get("idx") in admitted for item in changed),
        "claim_extraction_mode": "independent_per_model" if args.independent_claims else "joint",
        "d1_candidate_mode": "normalized_programmatic_pairs" if args.normalized_d1 else "all_claims_prompt",
        "normalization": {
            "indexed_claim_count": len(normalized),
            "indexed_claim_rate": len(normalized) / len(claims) if claims else 0,
            "row_count": len(normalization_rows),
            "unresolved_claim_count": len(unresolved_rows),
            "coverage_complete_record_count": coverage_complete_records,
            "blocked_record_count": blocked_normalization_records,
            "partial_record_count": partial_normalization_records,
            "candidate_pair_count": len(candidate_pairs),
            "records_with_candidate_pair": sum(bool(record.get("swarm_normalization", {}).get("candidate_pairs")) for record in records),
        },
        "diagnosis": {
            "enabled": args.diagnosis_gate,
            "status": dict(diagnosis_states),
            "eligible_record_count": diagnosis_states["ELIGIBLE"],
            "retained_a_pool_record_count": diagnosis_states["RETAIN_A_POOL"],
            "eligible_problem_types": dict(diagnosis_problem_types),
            "eligible_diagnosis_types": dict(diagnosis_error_types),
            "new_claim_labels": {label: count for label, count in new_claim_labels.items() if label},
            "note": "A non-eligible diagnosis is an explicit retain-A-pool route, not a negative claim about all source reasoning.",
        },
    }
    summary["gate_config"] = {
        "coreference_gate": args.coreference_gate,
        "field_span_gate": args.field_span_gate,
        "hbr_dedup": args.hbr_dedup,
        "grounded_normalization": args.grounded_normalization,
        "diagnosis_gate": args.diagnosis_gate,
    }
    if args.span_hybrid:
        raw_spans = [span for record in records for span in record.get("swarm_spans", {}).get("spans", [])]
        retrieved_pairs = [
            pair for record in records
            for pair in record.get("swarm_span_candidates", {}).get("candidate_pairs", [])
        ]
        span_candidate_status = Counter(
            record.get("swarm_span_candidates", {}).get("status", "MISSING") for record in records
        )
        localized = [record for record in records if record.get("swarm_conflict", {}).get("status") == "CONFLICT"]
        summary["span_hybrid"] = {
            "segmentation": "deterministic_sentence_or_line_offsets_v1",
            "raw_span_count": len(raw_spans),
            "records_with_complete_span_ledger": sum(
                record.get("swarm_spans", {}).get("status") == "DONE" for record in records
            ),
            "candidate_status": dict(span_candidate_status),
            "retrieved_cross_model_pair_count": len(retrieved_pairs),
            "records_with_retrieved_pair": sum(bool(record.get("swarm_span_candidates", {}).get("candidate_pairs")) for record in records),
            "localized_conflict_count": len(localized),
            "materialized_structured_claim_count": sum(
                len(record.get("swarm_conflict", {}).get("structured_claims", [])) for record in localized
            ),
            "note": "All source text is preserved as offset spans; structured claims are materialized only for admitted cross-model conflict candidates.",
        }
    _save_json(args.summary, summary)
    print(json.dumps(summary["conflict_localization"], ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("hard", "claims", "spans", "span_candidates", "diagnose", "normalize", "localize", "verify", "ledger", "guard", "clean", "rebuttal", "pool", "summary"))
    parser.add_argument("--model", choices=PARTICIPANTS, default="qwen")
    parser.add_argument("--source", default="outputs/qae_pooling_full_source_hard_v2.json")
    parser.add_argument("--out", default="outputs/qae_localized_disagreement_40.json")
    parser.add_argument("--summary", default="outputs/qae_localized_disagreement_40_summary.json")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--only-disagreement", action="store_true")
    parser.add_argument("--independent-claims", action="store_true", help="extract each frozen chain in a separate model call")
    parser.add_argument("--normalized-d1", action="store_true", help="localize only among program-generated normalized claim pairs")
    parser.add_argument("--strict-normalization", action="store_true", help="normalize every accepted claim individually and make partial semantic coverage explicit")
    parser.add_argument("--grounded-normalization", action="store_true", help="require exact source spans for normalized subject, predicate, and value")
    parser.add_argument("--compatible-d1", action="store_true", help="retrieve compatible subject/predicate pairs when one side leaves conditions unspecified")
    parser.add_argument("--span-hybrid", action="store_true", help="use lossless source spans and selective cross-model conflict materialization instead of full claim extraction")
    parser.add_argument("--diagnosis-gate", action="store_true", help="require a typed, source-pair-grounded diagnosis before span conflict localization")
    parser.add_argument("--span-candidate-limit", type=int, default=24, help="maximum program-retrieved cross-model span pairs per answer-disagreement record")
    parser.add_argument("--no-coreference-gate", dest="coreference_gate", action="store_false", help="ablation: permit standalone pronoun/article subjects")
    parser.add_argument("--no-field-span-gate", dest="field_span_gate", action="store_false", help="ablation: require exact spans but not field/span consistency")
    parser.add_argument("--no-hbr-dedup", dest="hbr_dedup", action="store_false", help="ablation: disable HBr alias/containment duplicate suppression")
    parser.set_defaults(coreference_gate=True, field_span_gate=True, hbr_dedup=True)
    args = parser.parse_args()
    records = _init(args)
    if args.stage == "hard": run_hard(args, records)
    elif args.stage == "claims": run_claims(args, records)
    elif args.stage == "spans": run_spans(args, records)
    elif args.stage == "span_candidates": run_span_candidates(args, records)
    elif args.stage == "diagnose": run_diagnose(args, records)
    elif args.stage == "normalize": run_normalize(args, records)
    elif args.stage == "localize": run_span_localize(args, records) if args.span_hybrid else run_localize(args, records)
    elif args.stage == "verify": run_span_verify(args, records) if args.span_hybrid else run_verify(args, records)
    elif args.stage == "ledger": run_ledger(args, records)
    elif args.stage == "guard": run_guard(args, records)
    elif args.stage == "clean": run_solve(args, records, "qae_clean", False)
    elif args.stage == "rebuttal": run_solve(args, records, "qae_rebuttal", True)
    elif args.stage == "pool": run_pool(args, records)
    else: _localized_summary(args, records)


if __name__ == "__main__":
    main()
