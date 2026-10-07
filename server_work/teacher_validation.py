# -*- coding: utf-8 -*-
"""
Teacher-script validation (主线 B evidence chain).

Three conditions share the SAME frozen initial responses and the SAME pooling stage;
only the "discussion mechanism" differs:
  A (baseline):      GoA pairwise_margin edges + 1-round S->T/T->S message passing + weighted mean pooling
  B (teacher full):  teacher divergence identification -> transactive revision round -> TAP deepen round
                     -> convergence check -> re-score + weighted mean pooling
  C (half script):   TAP self-completion round -> TAP deepen round (no cross-model transactive)
                     -> re-score + weighted mean pooling

Theories exercised: Roschelle (convergence = argument-level), Mercer (exploratory talk),
Berkowitz & Gibbs (transactive), Osborne TAP, Fischer/Weinberger (external script).
"""

import json
import re
import time
import os
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from modules import (
    node_sampling_model_card,
    edge_sampling,
    message_passing,
    graph_pooling,
    generate_initial_response_with_confidence,
)
from utils import generate_vllm, get_alphabet_choice

REF_MODELS = ["qwen", "qwen_coder", "mathstral", "biomedical_llama", "finance_llama", "saul"]
META = "qwen"
NUM_CHOICE = 4
TEMP = 0.7
MAX_TOKENS = 800
SEED = 0
TOP_K = 3
ROUNDS = 1
THRESHOLD = 0.05
DEEPSEEK_MODEL = "deepseek-chat"


def make_unique_node_names(sampled_nodes):
    from collections import Counter
    counts = Counter(sampled_nodes)
    seen = {}
    unique_names = []
    unique_to_original = {}
    for name in sampled_nodes:
        if counts[name] > 1:
            idx = seen.get(name, 0)
            unique_name = f"{name}_{idx}"
            seen[name] = idx + 1
        else:
            unique_name = name
        unique_names.append(unique_name)
        unique_to_original[unique_name] = name
    return unique_names, unique_to_original


def make_instruction(question):
    return (
        f"Question: {question}\n"
        "Provide your step-by-step reasoning first, and then print \"The answer is (x)\", "
        "where x is the answer choice (one capital letter), at the end of your response."
    )


FINAL_PROMPT = (
    "Please conclude by printing \"The answer is (x)\", where x is the answer choice "
    "(one capital letter), at the end of your response."
)


def _extract_letter(text):
    if not text:
        return None
    try:
        return get_alphabet_choice(text, num_choice=NUM_CHOICE)
    except Exception:
        hits = re.findall(r'[\(\[]\s*([A-Da-d])\s*[\)\]]', text)
        hits += re.findall(r'"answer"\s*:\s*"?([A-Da-d])', text)
        return hits[-1].upper() if hits else None


def _parse_json_loose(text):
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _sanitize(obj):
    """Recursively convert numpy scalars to native Python types for JSON dumping."""
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def _call(model_id, endpoint, prompt, max_tokens=700, temperature=0.2, debug_txt=""):
    out, _, _, _, _ = generate_vllm(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        endpoint=endpoint,
        debug_txt=debug_txt,
        seed=SEED,
    )
    return out


def _judge_cfg(judge_key="prometheus"):
    return model_endpoint_dict[judge_key]


# ---------------------------------------------------------------------------
# Two-layer divergence identification (deepseek-chat + deterministic)
# ---------------------------------------------------------------------------

_UNIT_WORDS = (
    "carbon", "atom", "atoms", "bond", "bonds", "ring", "rings", "proton", "protons",
    "electron", "electrons", "second", "seconds", "energy", "ev", "mev", "gev", "kev",
    "mol", "mole", "molar", "ml", "liter", "liters", "nm", "cm", "pm", "hz", "mhz", "ghz",
    "kelvin", "degree", "degrees", "ph", "v", "mv", "g", "mg", "kg", "j", "kj",
    "wavelength", "count", "fold", "times", "step", "steps",
)


def _numbers_with_context(chain):
    pairs = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![\w.])", chain):
        start, end = m.start(), m.end()
        ctx = (chain[max(0, start - 60):start] + " " + chain[end:end + 60]).lower()
        for w in _UNIT_WORDS:
            if re.search(r"\b" + re.escape(w) + r"\w*", ctx):
                pairs.append((m.group(1), w))
                break
    return pairs


def _deterministic_candidates(chains, initial_answers=None):
    answers = {}
    for i, c in enumerate(chains):
        a = None
        if initial_answers:
            a = initial_answers.get(str(i)) or initial_answers.get(i)
        answers[f"M{i}"] = a or _extract_letter(c) or "?"
    per_chain = [_numbers_with_context(c) for c in chains]
    by_kw = {}
    for ci, pairs in enumerate(per_chain):
        for num, kw in pairs:
            by_kw.setdefault(kw, {})[ci] = num
    numeric_candidates = []
    for kw, claims in by_kw.items():
        if len(claims) >= 2 and len(set(claims.values())) >= 2:
            numeric_candidates.append({
                "entity": kw,
                "claims": {f"M{i}": v for i, v in sorted(claims.items())},
            })
    return {"answers": answers, "numeric_candidates": numeric_candidates}


def _call_deepseek_json(prompt, max_tokens=3000, retries=3):
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        return "", "no_key"
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                data = json.loads(r.read().decode())
            return data["choices"][0]["message"]["content"], "ok"
        except Exception as e:
            print(f"  [deepseek divergence] failed ({attempt+1}): {e}")
            time.sleep(3)
    return "", "error"


def _deepseek_divergence_prompt(question, chains, candidates):
    blocks = "\n\n".join(
        f"M{i}:\n\"\"\"{(c[:2000] if c else c)}\"\"\"" for i, c in enumerate(chains)
    )
    cand_json = json.dumps(candidates, ensure_ascii=False)
    return (
        "You are a discussion moderator for a graduate-level science multiple-choice question.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Three reasoning chains:\n{blocks}\n\n"
        f"###Deterministic candidates already extracted (verify these, do not invent from nothing):\n"
        f"{cand_json}\n\n"
        "###Your task (output STRICT JSON only):\n"
        "1. answers: final answer letter of each chain (M0/M1/M2).\n"
        "2. fact_conflicts: for each numeric candidate, decide if it is a REAL factual conflict "
        "(same entity, incompatible numbers) or noise (e.g. option numbers, unrelated counts). "
        "Include only real conflicts. Also add any other clear factual conflicts you find "
        "(reagents, properties, conditions).\n"
        "3. reasoning_conflicts: incompatible reasoning claims between chains.\n"
        "4. self_contradictions: a single chain whose conclusion contradicts its own reasoning "
        "or numbers.\n\n"
        'Schema: {"answers": {"M0": "X", "M1": "X", "M2": "X"}, '
        '"fact_conflicts": [{"fact": "...", "claims": {"M0": "...", "M1": "..."}, '
        '"verdict": "conflict"}], '
        '"reasoning_conflicts": [{"claim": "...", "chains": {"M0": "...", "M1": "..."}}], '
        '"self_contradictions": [{"chain": "M1", "detail": "..."}]}'
    )


def identify_divergence(question, chains, initial_answers=None, use_prometheus_fallback=True):
    """Two-layer divergence: deterministic candidates -> deepseek-chat -> (fallback) prometheus."""
    det = _deterministic_candidates(chains, initial_answers)
    prompt = _deepseek_divergence_prompt(question, chains, det)
    raw, status = _call_deepseek_json(prompt)
    parsed = _parse_json_loose(raw)
    if parsed and parsed.get("answers"):
        return {"divergence": parsed, "raw": raw, "source": "deepseek", "det": det}
    if use_prometheus_fallback:
        judge = _judge_cfg("prometheus")
        try:
            raw2 = _call(judge["model_id"], judge["url"], divergence_prompt(question, chains),
                         max_tokens=700, debug_txt="[Teacher Divergence fallback] ")
            parsed2 = _parse_json_loose(raw2)
            if parsed2 and parsed2.get("answers"):
                return {"divergence": parsed2, "raw": raw2, "source": "prometheus", "det": det}
        except Exception as e:
            print(f"  [divergence] prometheus fallback failed: {e}")
    return {"divergence": det, "raw": raw, "source": "deterministic_only", "det": det}


# ---------------------------------------------------------------------------
# Teacher prompts
# ---------------------------------------------------------------------------

def divergence_prompt(question, responses):
    blocks = "\n\n".join(f"M{i}:\n\"\"\"{r}\"\"\"" for i, r in enumerate(responses))
    return (
        "###Task Description:\n"
        "A graduate-level science multiple-choice question and three candidate reasoning "
        "chains (M0/M1/M2) are given. Identify where the chains diverge.\n"
        "1. Extract each chain's final answer letter.\n"
        "2. List factual claims (numbers, reagents, reaction types, properties) that "
        "conflict between chains.\n"
        "3. List reasoning claims that conflict between chains, including self-"
        "contradictions inside a single chain.\n"
        "Output strictly JSON with this schema:\n"
        '{"answers": {"M0": "X", "M1": "X", "M2": "X"}, '
        '"fact_conflicts": [{"fact": "...", "claims": {"M0": "...", "M1": "..."}}], '
        '"reasoning_conflicts": [{"claim": "...", "chains": {"M0": "...", "M1": "..."}, '
        '"conflict": "..."}]}\n\n'
        "###Question:\n"
        f"{question}\n\n"
        "###Responses:\n"
        f"{blocks}\n\n"
        "###JSON:\n"
    )


def transactive_prompt(question, chain_i, chain_j, j_name):
    return (
        "You are in a guided discussion for a science multiple-choice question.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Another model ({j_name}) reasoned:\n\"\"\"{chain_j}\"\"\"\n\n"
        f"###Your previous reasoning:\n\"\"\"{chain_i}\"\"\"\n\n"
        "###Guided-discussion rule:\n"
        "Your answer must OPERATE ON the other model's reasoning (restate, then critique or "
        "complete it). Do NOT merely restate your own previous chain.\n"
        "1) Restate the other model's reasoning in your own words.\n"
        "2) State which step you agree with, and identify the exact step that breaks: a wrong "
        "fact, a missing warrant (why the data imply the claim), or a missing rebuttal "
        "(an alternative answer you failed to exclude). Give one concrete reason.\n"
        "3) Give your updated final answer: \"The answer is (X)\" plus 2-3 sentences of reasoning."
    )


def tap_prompt(question, chain_i, focus=None):
    focus_line = f"\nFocus especially on resolving: {focus}" if focus else ""
    return (
        "You are in a guided discussion for a science multiple-choice question.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Your current reasoning:\n\"\"\"{chain_i}\"\"\"\n\n"
        "###Task:\n"
        "Complete your argument in six fields:\n"
        "- claim: your final answer letter\n"
        "- data: the concrete facts/numbers/conditions from the question you rely on\n"
        "- warrant: why the data imply the claim (the reasoning link)\n"
        "- backing: the conditions under which your rule holds\n"
        "- rebuttal: how you exclude the main alternative answer\n"
        "- qualifier: the limits of your conclusion\n"
        f"{focus_line}\n"
        "Output JSON only with keys: claim, data, warrant, backing, rebuttal, qualifier, answer."
    )


def evidence_prompt(question, chain_i):
    return (
        "You are in a guided discussion for a science multiple-choice question.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Your current reasoning:\n\"\"\"{chain_i}\"\"\"\n\n"
        "###Task:\n"
        "Give INDEPENDENT evidence supporting YOUR conclusion. Do NOT refer to other "
        "models' answers or reasoning.\n"
        "1. data: the concrete facts/numbers/conditions from the question that support "
        "your claim\n"
        "2. warrant: why these data imply your claim (the reasoning link)\n"
        "3. backing: the conditions under which your rule holds\n"
        "4. rebuttal: how you rule out the main alternative answer\n"
        "Then give your final answer: \"The answer is (X)\" plus 2-3 sentences of reasoning."
    )


def verify_prompt(question, chain_i):
    return (
        "You are in a guided discussion for a science multiple-choice question.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Your current reasoning:\n\"\"\"{chain_i}\"\"\"\n\n"
        "###Task (independent verification):\n"
        "1. Re-check every number, reagent, and condition you relied on against the "
        "question text. Correct any error explicitly.\n"
        "2. State whether your conclusion still holds after re-checking, and why.\n"
        "3. Give your final answer: \"The answer is (X)\" plus 2-3 sentences of reasoning."
    )


def convergence_prompt(question, revised):
    blocks = "\n\n".join(f"M{i}:\n\"\"\"{r}\"\"\"" for i, r in enumerate(revised))
    return (
        "###Task Description:\n"
        "Three models discussed a science multiple-choice question and each produced a "
        "revised reasoning chain. Determine convergence.\n"
        "1. Extract each chain's final answer letter.\n"
        "2. State the key warrant/fact each chain relies on to support its answer.\n"
        "3. Classify convergence:\n"
        '   - "argument": same answer letter AND compatible key warrant/fact (argument-level convergence)\n'
        '   - "answer_only": same answer letter but conflicting or incompatible reasoning\n'
        '   - "not_converged": different answer letters\n'
        "Output strictly JSON: {\"answers\": {\"M0\": \"X\", ...}, "
        "\"key_warrants\": {\"M0\": \"...\", ...}, \"convergence\": \"argument\"}\n\n"
        "###Question:\n"
        f"{question}\n\n"
        "###Revised chains:\n"
        f"{blocks}\n\n"
        "###JSON:\n"
    )


# ---------------------------------------------------------------------------
# Condition implementations
# ---------------------------------------------------------------------------

def run_baseline(models_dict_unique, model_name_idx, initial_responses, confidences, instruction):
    """Condition A: exact GoA baseline (pairwise_margin + 1-round message passing + weighted mean pooling)."""
    output = edge_sampling(
        models_dict=models_dict_unique,
        model_name_idx=model_name_idx,
        initial_responses=initial_responses,
        messages=[instruction],
        threshold=THRESHOLD,
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        seed=SEED,
        confidences=confidences,
        edge_mode="pairwise_margin",
    )
    meta_cfg = model_endpoint_dict[META]
    if not isinstance(output, tuple):
        final_response, _, _ = graph_pooling(
            model=meta_cfg["model_id"],
            endpoint=meta_cfg["url"],
            refined_response=initial_responses,
            messages=[instruction],
            temperature=TEMP,
            max_tokens=MAX_TOKENS,
            final_prompt=FINAL_PROMPT,
            seed=SEED,
        )
        return final_response, {}, "fallback_mean"

    source_edges, target_edges, score_dict, _sm, _fb, _fbe, _it, _ot, target_weights = output
    round_responses = dict(initial_responses)
    for _round in range(ROUNDS):
        _s2t, t2s, _it, _ot = message_passing(
            model_endpoint_dict=models_dict_unique,
            model_name_idx=model_name_idx,
            initial_responses=round_responses,
            source_edges=source_edges,
            target_edges=target_edges,
            score_dict=score_dict,
            source_with_most_edges=None,
            messages=[instruction],
            temperature=TEMP,
            max_tokens=MAX_TOKENS,
            round=f"{_round+1}/{ROUNDS}",
            final_prompt=FINAL_PROMPT,
            seed=SEED,
            target_weights=target_weights,
            anti_sycophancy=False,
        )
        round_responses = dict(t2s)

    final_response, _, _ = graph_pooling(
        model=meta_cfg["model_id"],
        endpoint=meta_cfg["url"],
        refined_response=round_responses,
        weights=score_dict,
        messages=[instruction],
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        final_prompt=FINAL_PROMPT,
        seed=SEED,
    )
    return final_response, score_dict, "goa"


def run_teacher(models_dict_unique, model_name_idx, initial_responses, instruction, transactive=True):
    """Condition B (transactive=True) or C (transactive=False)."""
    judge = _judge_cfg("prometheus")
    q = instruction.replace("Question: ", "", 1).split("\nProvide your step-by-step")[0]
    chains = list(initial_responses.values())

    # --- Step 1: two-layer divergence identification (deepseek-chat + deterministic) ---
    div_info = identify_divergence(q, chains)
    div = div_info["divergence"]
    div_raw = div_info["raw"]
    div_source = div_info["source"]

    # --- Step 2: revision rounds ---
    revised = dict(initial_responses)
    round1_meta = {}
    for i, un in enumerate(model_name_idx.values()):
        chain_i = revised[i]
        node_cfg = models_dict_unique[un]
        if transactive:
            # pick partner with a different answer if possible
            my_ans = _extract_letter(chain_i)
            partners = [j for j in range(len(chains)) if j != i and _extract_letter(chains[j]) != my_ans]
            j = partners[0] if partners else (i + 1) % len(chains)
            prompt = transactive_prompt(q, chain_i, chains[j], f"M{j}")
            round1_meta[i] = {"partner": j}
        else:
            prompt = tap_prompt(q, chain_i)
            round1_meta[i] = {"partner": None}
        out = _call(node_cfg["model_id"], node_cfg["url"],
                    prompt, max_tokens=MAX_TOKENS, temperature=TEMP,
                    debug_txt=f"[Teacher R1 {un}] ")
        revised[i] = out

    # --- Step 3: TAP deepen round with focus on top conflict ---
    focus = None
    if div.get("reasoning_conflicts"):
        focus = str(div["reasoning_conflicts"][0])
    elif div.get("fact_conflicts"):
        focus = str(div["fact_conflicts"][0])
    elif div.get("self_contradictions"):
        focus = str(div["self_contradictions"][0])
    round2_meta = {}
    for i, un in enumerate(model_name_idx.values()):
        node_cfg = models_dict_unique[un]
        prompt = tap_prompt(q, revised[i], focus=focus)
        out = _call(node_cfg["model_id"], node_cfg["url"],
                    prompt, max_tokens=MAX_TOKENS, temperature=TEMP,
                    debug_txt=f"[Teacher R2 {un}] ")
        revised[i] = out
        round2_meta[i] = {"focus": bool(focus)}

    # --- Step 4: convergence check (condition B only) ---
    conv = None
    if transactive:
        conv_raw = _call(judge["model_id"], judge["url"], convergence_prompt(q, list(revised.values())),
                         max_tokens=500, debug_txt="[Teacher Convergence] ")
        conv = _parse_json_loose(conv_raw)

    # --- Step 5: identical pooling stage (re-score + weighted mean) ---
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
        "divergence_raw": div_raw,
        "divergence_source": div_source,
        "convergence": conv,
        "revised_chains": revised,
        "round1_meta": round1_meta,
        "round2_meta": round2_meta,
    }


def run_evidence_condition(models_dict_unique, model_name_idx, initial_responses, instruction):
    """Condition D: teacher asks ONLY for independent evidence + self-verification.
    No cross-model reference, no transactive, no conflict-based steering."""
    q = instruction.replace("Question: ", "", 1).split("\nProvide your step-by-step")[0]
    revised = dict(initial_responses)
    for rnd, prompt_fn in [("R1", evidence_prompt), ("R2", verify_prompt)]:
        for i, un in enumerate(model_name_idx.values()):
            node_cfg = models_dict_unique[un]
            out = _call(node_cfg["model_id"], node_cfg["url"],
                        prompt_fn(q, revised[i]), max_tokens=MAX_TOKENS, temperature=TEMP,
                        debug_txt=f"[TeacherD {rnd} {un}] ")
            revised[i] = out

    # identical pooling stage: re-score + weighted mean
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
        "revised_chains": revised,
    }


# ---------------------------------------------------------------------------
# Per-question orchestration
# ---------------------------------------------------------------------------

def run_one(item):
    idx = item["idx"]
    question = item["question"]
    gold = item["gold_answer"]
    instruction = make_instruction(question)
    result = {"idx": idx, "gold": gold}
    t0 = time.time()

    # Node sampling (identical across conditions)
    meta_cfg = model_endpoint_dict[META]
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    sampled_nodes, _fallback, _it, _ot = node_sampling_model_card(
        model=meta_cfg["model_id"], endpoint=meta_cfg["url"], messages=[instruction],
        model_info_dict=models_dict, top_k=TOP_K, temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
    )
    unique_names, unique_to_original = make_unique_node_names(sampled_nodes)
    models_dict_unique = {un: models_dict[unique_to_original[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    initial_responses, confidences = {}, {}
    for i, un in enumerate(unique_names):
        raw, ans, conf, _it, _ot = generate_initial_response_with_confidence(
            model_id=models_dict_unique[un]["model_id"], endpoint=models_dict_unique[un]["url"],
            instruction=instruction, data="GPQA", num_choice=NUM_CHOICE,
            temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
            debug_txt=f"[Initial {un}] ",
        )
        initial_responses[i] = raw
        confidences[i] = conf

    result["sampled_nodes"] = sampled_nodes
    result["unique_names"] = unique_names
    result["initial_responses"] = initial_responses
    result["initial_answers"] = {i: _extract_letter(r) for i, r in initial_responses.items()}

    # Condition A: baseline
    try:
        fa, score_a, note_a = run_baseline(models_dict_unique, model_name_idx, initial_responses, confidences, instruction)
        result["A"] = {"answer": _extract_letter(fa), "final_response": fa, "pool_note": note_a, "score_dict": score_a}
    except Exception as e:
        result["A"] = {"error": str(e)}
        print(f"[{idx}] A error: {e}", flush=True)

    # Condition B: teacher full (transactive)
    try:
        rb = run_teacher(models_dict_unique, model_name_idx, initial_responses, instruction, transactive=True)
        result["B"] = {
            "answer": rb["answer"], "final_response": rb["final_response"],
            "score_dict": rb["score_dict"], "pool_note": rb["pool_note"],
            "divergence": rb["divergence"], "divergence_raw": rb["divergence_raw"],
            "convergence": rb["convergence"],
            "revised_chains": rb["revised_chains"],
            "round1_meta": rb["round1_meta"],
        }
    except Exception as e:
        result["B"] = {"error": str(e)}
        print(f"[{idx}] B error: {e}", flush=True)

    # Condition C: half script (TAP only)
    try:
        rc = run_teacher(models_dict_unique, model_name_idx, initial_responses, instruction, transactive=False)
        result["C"] = {
            "answer": rc["answer"], "final_response": rc["final_response"],
            "score_dict": rc["score_dict"], "pool_note": rc["pool_note"],
            "divergence": rc["divergence"],
            "revised_chains": rc["revised_chains"],
            "round1_meta": rc["round1_meta"],
        }
    except Exception as e:
        result["C"] = {"error": str(e)}
        print(f"[{idx}] C error: {e}", flush=True)

    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{idx}] done in {result['time_s']}s | gold={gold} | "
          f"A={result.get('A', {}).get('answer')} B={result.get('B', {}).get('answer')} "
          f"C={result.get('C', {}).get('answer')}", flush=True)
    return result


def run_teacher_only(item, initials_by_idx, condition="B"):
    """Re-run teacher conditions on FROZEN initial responses (control variable)."""
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

    if condition == "D":
        result["time_s"] = round(time.time() - t0, 1)
        rd = run_evidence_condition(models_dict_unique, model_name_idx, initial_responses, instruction)
        result["D"] = {
            "answer": rd["answer"], "final_response": rd["final_response"],
            "score_dict": rd["score_dict"], "pool_note": rd["pool_note"],
            "revised_chains": rd["revised_chains"],
        }
        print(f"[{idx}] done in {result['time_s']}s | gold={gold} | D={result['D'].get('answer')}", flush=True)
    else:
        result["time_s"] = round(time.time() - t0, 1)
        rb = run_teacher(models_dict_unique, model_name_idx, initial_responses, instruction, transactive=True)
        result["B"] = {
            "answer": rb["answer"], "final_response": rb["final_response"],
            "score_dict": rb["score_dict"], "pool_note": rb["pool_note"],
            "divergence": rb["divergence"], "divergence_raw": rb["divergence_raw"],
            "divergence_source": rb["divergence_source"],
            "convergence": rb["convergence"],
            "revised_chains": rb["revised_chains"],
            "round1_meta": rb["round1_meta"],
        }
        print(f"[{idx}] done in {result['time_s']}s | gold={gold} | B={result['B'].get('answer')} "
              f"src={rb['divergence_source']}", flush=True)
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--idxs_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reuse_initials", default=None, help="path to teacher_val_40.json with frozen initial responses")
    ap.add_argument("--condition", default="B", choices=["B", "D"])
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    with open(args.idxs_path) as f:
        idxs = json.load(f)
    subset = [dict(s, idx=i) for i, s in enumerate(samples) if i in idxs]
    if args.limit:
        subset = subset[: args.limit]
    print(f"[TeacherVal] questions: {len(subset)}", flush=True)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    initials_by_idx = {}
    if args.reuse_initials:
        with open(args.reuse_initials) as f:
            old_results = json.load(f)
        initials_by_idx = {r["idx"]: r for r in old_results}
        print(f"[TeacherVal] reusing frozen initial responses from {args.reuse_initials}", flush=True)

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        if args.reuse_initials:
            futs = {ex.submit(run_teacher_only, item, initials_by_idx, args.condition): item["idx"] for item in subset}
        else:
            futs = {ex.submit(run_one, item): item["idx"] for item in subset}
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
            print(f"[TeacherVal] progress {done}/{len(subset)}", flush=True)

    print(f"[TeacherVal] saved {len(results)} results to {args.out}", flush=True)


if __name__ == "__main__":
    main()
