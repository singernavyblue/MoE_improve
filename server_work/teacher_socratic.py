# -*- coding: utf-8 -*-
"""
Socratic Scaffolding teacher condition (Condition S).

Theory mapping:
  - Bloom (1984) 2-sigma: tutor-style guidance is the treatment under test.
  - Mayer (2004) guided discovery: teacher gives HINTS, never answers.
  - Graesser AutoTutor (2004): dialogue moves PUMP/HINT/PROMPT/FEEDBACK;
    forbidden move = ASSERTION (stating facts/answers).
  - Vygotsky ZPD: hint ladder L0(meta/reading) -> L1(locate) -> L2(concept) -> L3(counterexample),
    from outer to inner ZPD.
  - Roschelle (1992): divergence is the starting point; convergence checked at pooling.
  - Berkowitz & Gibbs (1983): student must restate the hint before answering (transactive).
  - Mercer (1996): teacher targets the minority-answer holder first (protect minority voice).

Control variables (same as previous teacher conditions):
  - SAME frozen initial responses (reuse teacher_val_40.json)
  - SAME node sampling
  - SAME pooling stage (pairwise_margin re-score + weighted mean)
  Only the discussion mechanism differs.
"""

import json
import re
import time
import os
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from teacher_validation import (
    make_unique_node_names,
    run_baseline,
    identify_divergence,
    _call,
    _extract_letter,
    _parse_json_loose,
    _sanitize,
    _call_deepseek_json,
    REF_MODELS,
    META,
    NUM_CHOICE,
    TEMP,
    MAX_TOKENS,
    SEED,
    TOP_K,
    THRESHOLD,
    make_instruction,
    FINAL_PROMPT,
)
from modules import edge_sampling, graph_pooling


# ---------------------------------------------------------------------------
# Hint ladder definitions
# ---------------------------------------------------------------------------

LEVEL_DEFS = {
    "L0": {
        "name": "metacognition / question alignment",
        "instruction": (
            "Ask the model to restate what the question actually asks (including all "
            "qualifiers such as except/not/which-is-wrong), and to name which sentence "
            "of the question its conclusion relies on. Do NOT evaluate correctness."
        ),
        "fallback": (
            "先用自己的话复述这道题问的是什么（注意 except/not 这类限定词），"
            "然后指出你的结论基于题干里的哪一句话。"
        ),
    },
    "L1": {
        "name": "locate the step",
        "instruction": (
            "Ask the model to locate the exact step in its own reasoning chain whose "
            "premise is NOT directly given by the question text (an assumed fact, a "
            "skipped condition, or a number it invented). Do NOT say which step is wrong."
        ),
        "fallback": (
            "检查你自己的推理链：找出一步其依据并不是题干直接给出的步骤"
            "（比如假设的事实、跳过的条件、或自己算出来的数字），指出是第几步。"
        ),
    },
    "L2": {
        "name": "concept / conservation check",
        "instruction": (
            "Ask a concept-level question whose answer is implied by the question's own "
            "facts (e.g. 'does catalytic hydrogenation change the carbon skeleton?' for a "
            "carbon-count problem). The question must be answerable from common science "
            "knowledge and must not contain an answer letter or the word 'correct/wrong'."
        ),
        "fallback": (
            "这道题涉及的核心原理/守恒关系是什么？"
            "你的推理里有没有某一步与这个原理不一致？"
        ),
    },
    "L3": {
        "name": "counterexample / eliminate alternative",
        "instruction": (
            "Ask the model to check whether its own conclusion survives the question's "
            "facts taken together, and to explicitly test at least one alternative answer "
            "it has NOT yet ruled out. Do NOT name which alternative is right."
        ),
        "fallback": (
            "如果题干的全部事实必须同时成立，你的结论还能成立吗？"
            "请显式检验一个你还没有排除的替代选项。"
        ),
    },
}

LADDER = ["L0", "L1", "L2"]  # v1: fixed ladder, 3 rounds max
MAX_ROUNDS = 3


def _socratic_hint_prompt(question, chain, level, target_label):
    lv = LEVEL_DEFS[level]
    return (
        "You are a Socratic tutor for a graduate-level science multiple-choice question. "
        "You NEVER give the answer. You ask one short question at a time.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Student ({target_label}) current reasoning:\n\"\"\"{chain[:2000]}\"\"\"\n\n"
        f"###Your task for level {level} ({lv['name']}):\n{lv['instruction']}\n\n"
        "###Constraints:\n"
        "1. Reference ONLY facts already present in the question text or universally "
        "accepted background knowledge. Do NOT introduce new specific facts.\n"
        "2. Do NOT output any answer letter (A/B/C/D).\n"
        "3. Do NOT say 'correct', 'wrong', or 'the answer is'.\n"
        "4. One question only, at most 40 words, in the language of the student's chain.\n\n"
        'Output STRICT JSON only: {"move": "HINT", "level": "' + level + '", "where": "<step location or aspect>", "prompt": "<the question text>"}'
    )


def _socratic_student_prompt(question, chain, hint_text, hint_json=None):
    hint_block = hint_text
    if hint_json:
        try:
            hint_block = (
                f"[Move: {hint_json.get('move')} | Level: {hint_json.get('level')} | "
                f"Where: {hint_json.get('where')}]\nQuestion: {hint_json.get('prompt')}"
            )
        except Exception:
            hint_block = hint_text
    return (
        "You are a student in a Socratic tutorial for a science multiple-choice question. "
        "The tutor will ask you one question. Follow the format EXACTLY:\n"
        "1. [Restate] Restate the tutor's question in your own words.\n"
        "2. [Revise] Yes or No — whether you change your final answer after thinking.\n"
        "3. [Reason] Give the reasoning step you now see (if Yes, state what you correct; "
        "if No, explain why the question does not change your answer).\n"
        "4. Then give your full updated reasoning and end with \"The answer is (X)\".\n\n"
        f"###Question:\n{question}\n\n"
        f"###Your previous reasoning:\n\"\"\"{chain}\"\"\"\n\n"
        f"###Tutor question:\n{hint_block}\n"
    )


def _rule_hint(level, question):
    return LEVEL_DEFS[level]["fallback"]


def _gen_hint(question, chain, level, target_label):
    """Generate one hint. DeepSeek first; rule-based fallback on any failure."""
    prompt = _socratic_hint_prompt(question, chain, level, target_label)
    raw, status = _call_deepseek_json(prompt, max_tokens=400, retries=2)
    parsed = _parse_json_loose(raw)
    if parsed and parsed.get("prompt"):
        return {
            "source": "deepseek",
            "raw": raw,
            "hint_json": parsed,
            "hint_text": parsed["prompt"],
        }
    return {
        "source": "rule",
        "raw": raw,
        "hint_json": {"move": "HINT", "level": level, "where": "self-chain", "prompt": _rule_hint(level, question)},
        "hint_text": _rule_hint(level, question),
    }


def _parse_revise(reply):
    """Extract Revise: Yes/No, new answer letter, and whether a reason is present."""
    m = re.search(r"\[Revise\]\s*(Yes|No)", reply, re.IGNORECASE)
    revise = m.group(1).lower() if m else None
    ans = _extract_letter(reply)
    has_reason = bool(re.search(r"\[Reason\]|理由|because|since", reply, re.IGNORECASE))
    return {"revise": revise, "answer": ans, "has_reason": has_reason}


def _collect_flagged(div):
    """Collect model indices that divergence detection marks with a substantive flaw."""
    flagged = set()
    counts = {}
    div = div or {}
    for fc in div.get("fact_conflicts") or []:
        for k in (fc.get("claims") or {}):
            m = re.match(r"M(\d)", str(k))
            if m:
                idx = int(m.group(1))
                flagged.add(idx)
                counts[idx] = counts.get(idx, 0) + 1
    for rc in div.get("reasoning_conflicts") or []:
        for k in (rc.get("chains") or {}):
            m = re.match(r"M(\d)", str(k))
            if m:
                idx = int(m.group(1))
                flagged.add(idx)
                counts[idx] = counts.get(idx, 0) + 1
    for sc in div.get("self_contradictions") or []:
        m = re.match(r"M(\d)", str(sc.get("chain", "")))
        if m:
            idx = int(m.group(1))
            flagged.add(idx)
            counts[idx] = counts.get(idx, 0) + 1
    return flagged, counts


def _select_target(div, chains, initial_answers):
    """v2: only hint models with BOTH an extractable answer AND a substantive flaw
    (fact/reasoning conflict or self-contradiction). No flaw -> no intervention."""
    n = len(chains)
    letters = [initial_answers.get(i) or _extract_letter(chains[i]) for i in range(n)]
    valid = [i for i in range(n) if letters[i] and letters[i] != "?"]
    if not valid:
        return None, "no_valid_model"
    flagged, counts = _collect_flagged(div)
    cands = [i for i in valid if i in flagged]
    if not cands:
        return None, "no_substantive_flaw"
    best = max(counts.get(i, 0) for i in cands)
    top = sorted(i for i in cands if counts.get(i, 0) == best)
    # tie-break: prefer the answer letter that is in the minority among valid models,
    # then lower index (stable).
    from collections import Counter
    lc = Counter(letters[i] for i in valid)
    top.sort(key=lambda i: (lc[letters[i]], i))
    return top[0], "substantive_flaw"


def run_socratic(models_dict_unique, model_name_idx, initial_responses, instruction):
    """Condition S v2: Socratic hint ladder ONLY on a model with an extractable answer
    AND a substantive flaw; otherwise no intervention (pool original chains)."""
    q = instruction.replace("Question: ", "", 1).split("\nProvide your step-by-step")[0]
    chains = list(initial_responses.values())
    initial_answers = {i: _extract_letter(c) for i, c in enumerate(chains)}

    # Step 1: divergence (same as other teacher conditions)
    div_info = identify_divergence(q, chains, initial_answers=initial_answers)
    div = div_info["divergence"]

    # Step 2: pick target (v2: exclude N/A, require substantive flaw)
    target, why = _select_target(div, chains, initial_answers)
    intervened = target is not None
    revised = dict(initial_responses)
    hint_log = []

    if intervened:
        target_un = model_name_idx[target]
        node_cfg = models_dict_unique[target_un]
        no_count = 0
        prev_answer = initial_answers.get(target)
        for rnd, level in enumerate(LADDER[:MAX_ROUNDS], start=1):
            gen = _gen_hint(q, revised[target], level, f"M{target}")
            hint_text = gen["hint_text"]
            student_prompt = _socratic_student_prompt(q, revised[target], hint_text, gen["hint_json"])
            reply = _call(
                node_cfg["model_id"], node_cfg["url"],
                student_prompt, max_tokens=MAX_TOKENS, temperature=TEMP,
                debug_txt=f"[Socratic R{rnd} L{level} {target_un}] ",
            )
            parsed = _parse_revise(reply)
            new_answer = parsed["answer"]
            changed = (new_answer != prev_answer) and bool(prev_answer) and bool(new_answer)
            hint_log.append({
                "round": rnd, "level": level, "hint_source": gen["source"],
                "hint_text": hint_text, "hint_raw": gen["raw"],
                "student_reply": reply,
                "revise": parsed["revise"], "new_answer": new_answer,
                "changed": changed, "has_reason": parsed["has_reason"],
            })
            revised[target] = reply
            if parsed["revise"] == "no":
                no_count += 1
            else:
                no_count = 0
            prev_answer = new_answer
            if no_count >= 2:
                break  # hints not landing: stop early

    # Step 3/4: identical pooling (pairwise_margin re-score + weighted mean)
    output = edge_sampling(
        models_dict=models_dict_unique,
        model_name_idx=model_name_idx,
        initial_responses=revised,
        messages=[instruction],
        threshold=THRESHOLD,
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        seed=SEED,
        confidences=None,
        edge_mode="pairwise_margin",
    )
    meta_cfg = model_endpoint_dict[META]
    if not isinstance(output, tuple):
        final_response, _, _ = graph_pooling(
            model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
            refined_response=revised, messages=[instruction],
            temperature=TEMP, max_tokens=MAX_TOKENS, final_prompt=FINAL_PROMPT, seed=SEED,
        )
        score_dict = {}
        pool_note = "fallback_mean"
    else:
        _s, _t, score_dict, _sm, _fb, _fbe, _it, _ot, _tw = output
        final_response, _, _ = graph_pooling(
            model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
            refined_response=revised, weights=score_dict, messages=[instruction],
            temperature=TEMP, max_tokens=MAX_TOKENS, final_prompt=FINAL_PROMPT, seed=SEED,
        )
        pool_note = "weighted_mean"

    return {
        "final_response": final_response,
        "answer": _extract_letter(final_response),
        "score_dict": score_dict,
        "pool_note": pool_note,
        "divergence": div,
        "divergence_raw": div_info["raw"],
        "divergence_source": div_info["source"],
        "intervened": intervened,
        "target": target,
        "target_model": model_name_idx[target] if intervened else None,
        "target_reason": why,
        "hint_log": hint_log,
        "revised_chains": revised,
    }


def run_one_socratic(item, initials_by_idx, run_ab=True):
    old = initials_by_idx.get(item["idx"])
    if not old:
        raise ValueError(f"no frozen initials for idx {item['idx']}")
    idx = item["idx"]
    question = item["question"]
    gold = item["gold_answer"]
    instruction = make_instruction(question)
    result = {"idx": idx, "gold": gold}
    t0 = time.time()

    sampled_nodes = old["sampled_nodes"]
    unique_names = old["unique_names"]
    initial_responses = {int(k): v for k, v in sorted(old["initial_responses"].items())}
    initial_answers = {int(k): v for k, v in sorted((old.get("initial_answers") or {}).items())}
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    _u_names, u_to_orig = make_unique_node_names(sampled_nodes)
    models_dict_unique = {un: models_dict[u_to_orig[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    result["sampled_nodes"] = sampled_nodes
    result["unique_names"] = unique_names
    result["initial_responses"] = initial_responses
    result["initial_answers"] = initial_answers

    # matched baseline re-run on the same frozen initials (same process, same seeds)
    if run_ab:
        try:
            fa, score_a, note_a = run_baseline(
                models_dict_unique, model_name_idx, initial_responses, None, instruction
            )
            result["A_re"] = {
                "answer": _extract_letter(fa), "final_response": fa,
                "pool_note": note_a, "score_dict": score_a,
            }
        except Exception as e:
            result["A_re"] = {"error": str(e)}
            print(f"[{idx}] A_re error: {e}", flush=True)

    try:
        rs = run_socratic(models_dict_unique, model_name_idx, initial_responses, instruction)
        result["S"] = {
            "answer": rs["answer"], "final_response": rs["final_response"],
            "score_dict": rs["score_dict"], "pool_note": rs["pool_note"],
            "divergence": rs["divergence"], "divergence_raw": rs["divergence_raw"],
            "divergence_source": rs["divergence_source"],
            "target": rs["target"], "target_model": rs["target_model"],
            "target_reason": rs["target_reason"],
            "hint_log": rs["hint_log"], "revised_chains": rs["revised_chains"],
        }
    except Exception as e:
        result["S"] = {"error": str(e)}
        print(f"[{idx}] S error: {e}", flush=True)

    result["time_s"] = round(time.time() - t0, 1)
    a_old = old.get("A", {}).get("answer")
    print(
        f"[{idx}] done in {result['time_s']}s | gold={gold} | A_old={a_old} "
        f"A_re={result.get('A_re', {}).get('answer')} S={result.get('S', {}).get('answer')}",
        flush=True,
    )
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--idxs_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reuse_initials", required=True)
    ap.add_argument("--no_ab", action="store_true", help="skip re-running baseline A")
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    with open(args.idxs_path) as f:
        idxs = json.load(f)
    subset = [dict(s, idx=i) for i, s in enumerate(samples) if i in idxs]
    if args.limit:
        subset = subset[: args.limit]
    print(f"[Socratic] questions: {len(subset)}", flush=True)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.reuse_initials) as f:
        old_results = json.load(f)
    initials_by_idx = {r["idx"]: r for r in old_results}
    print(f"[Socratic] reusing frozen initial responses from {args.reuse_initials}", flush=True)

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(run_one_socratic, item, initials_by_idx, not args.no_ab): item["idx"]
            for item in subset
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
                results.append(_sanitize(r))
                with open(args.out, "w") as f:
                    json.dump(results, f, ensure_ascii=False, indent=1)
            except Exception as e:
                print(f"[worker] fatal: {e}", flush=True)
            print(f"[Socratic] progress {done}/{len(subset)}", flush=True)

    print(f"[Socratic] saved {len(results)} results to {args.out}", flush=True)


if __name__ == "__main__":
    main()
