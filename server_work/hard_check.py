# -*- coding: utf-8 -*-
"""
Deterministic hard checks (zero domain knowledge, zero model calls).

Theory mapping:
  - Verification is easier than generation (Cobbe 2021; Lightman 2023):
    local structural checks need no global answer.
  - A self-contradictory / content-free chain cannot be a correct answer
    (necessary-condition logic).
  - ECD (Mislevy 2003): score by checking observable evidence points, not by
    holistic impression.
  - Facione D3 / Toulmin: the chain's final claim must be backed by reasoning
    and must not contradict its own conclusion statements.

Enabled vetoes (calibrated on the frozen 40-question set, 0 false vetoes):
  - empty_reasoning: after stripping answer-statement boilerplate, the chain
    contains almost no reasoning content (len < 80).
  - multi_answer_conflict: the chain self-claims >=2 DIFFERENT final letters
    (e.g. "The answer is (A) and (B)." or "answer": "D" after "answer is C").

Record-only (may cause false positives):
  - no_self_answer: no final-answer statement found by our patterns.
"""

import re


_ANSWER_PATTERNS = [
    re.compile(r'"answer"\s*:\s*"?\s*([A-Da-d])'),
    re.compile(r'[Tt]he answer is\s*\(?([A-Da-d])'),
    re.compile(r'Answer\s*:\s*([A-Da-d])'),
    re.compile(r'[Aa]nswer is\s*([A-Da-d])'),
]


def self_claimed_answers(chain):
    """All final-answer letters the chain states about itself."""
    out = []
    for pat in _ANSWER_PATTERNS:
        for m in pat.finditer(chain):
            out.append(m.group(1).upper())
    # "The answer is (A) and (B)." multi-letter
    for m in re.finditer(r'[Tt]he answer is\s*\(?([A-Da-d])\)?[^A-Za-z]{0,8}and\s*\(?([A-Da-d])', chain):
        out.append(m.group(1).upper())
        out.append(m.group(2).upper())
    return out


def reasoning_content_len(chain):
    """Length of reasoning text after stripping answer statements / JSON keys."""
    t = re.sub(r'"answer"\s*:\s*"?[A-Da-d]*"?', '', chain)
    t = re.sub(r'[Tt]he answer is[^\n]{0,60}', '', t)
    t = re.sub(r'Answer\s*:[^\n]{0,20}', '', t)
    t = re.sub(r'[Aa]nswer is\s*\(?[A-Da-d]?\)?[^\n]{0,20}', '', t)
    t = re.sub(r'"confidence_level"\s*:\s*[\d.]+', '', t)
    t = re.sub(r'[{}"\\]', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return len(t.strip())


EMPTY_REASONING_LEN = 80


def hard_check_chain(chain):
    """Return list of violation labels for one chain."""
    flags = []
    sa = self_claimed_answers(chain)
    if len(set(sa)) > 1:
        flags.append("multi_answer_conflict:" + ",".join(sorted(set(sa))))
    rl = reasoning_content_len(chain)
    if rl < EMPTY_REASONING_LEN:
        flags.append(f"empty_reasoning(len={rl})")
    if not sa and rl >= EMPTY_REASONING_LEN:
        flags.append("no_self_answer")  # record-only
    return flags


def veto_flags(flags):
    """Violations that actually exclude a chain (medium gate)."""
    return [f for f in flags if f.startswith(("multi_answer_conflict", "empty_reasoning"))]
