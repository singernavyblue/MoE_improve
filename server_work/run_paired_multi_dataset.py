# -*- coding: utf-8 -*-
"""
Paired multi-dataset experiment: ORIGINAL GoA mutual-evaluation reproduction
(A_orig) vs the DeepSeek judge-led interrogation closed loop (J), on the SAME
frozen initial chains per question.

Datasets (option-A quick paired subsets):
  mmlu      : data/test/MMLU_sampled_test.json    -> random 200
  mmlu_pro  : data/test/MMLU_Pro_sampled_test.json-> random 200  (A-J)
  math      : data/test/MATH_test.json            -> random 100  (boxed answers)
  medmcqa   : data/test/MedMCQA_sampled_test.json -> all 100
  humaneval : data/dev/human_eval_dev.json        -> all 50    (pass@1 by unit tests)

A_orig = exact GoA_orig pipeline: node sampling -> initial responses ->
confidence replacement -> mutual edge scoring -> 1-round S->T/T->S message
passing -> qwen weighted-mean pooling.
J      = same frozen chains: each node gives INDEPENDENT new evidence ->
DeepSeek adjudicator picks one winner -> winner's INITIAL answer is final.

Run from /root/GoA_orig (imports its modules/utils/endpoint).
"""

import os
import sys
import json
import re
import time
import math
import random
import argparse
import subprocess
import urllib.request
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from endpoint import model_endpoint_dict
from modules import (
    node_sampling_model_card,
    generate_initial_response_with_confidence,
    maybe_replace_with_general,
    edge_sampling,
    message_passing,
    graph_pooling,
)
from utils import (
    generate_vllm,
    get_alphabet_choice,
    parse_confidence_response,
    extract_human_eval_completion,
    last_boxed_only_string,
    remove_boxed,
    is_math_equiv,
)

REF_MODELS = ["qwen", "qwen_coder", "mathstral", "biomedical_llama", "finance_llama", "saul"]
META = "qwen"
TEMP = 0.7
MAX_TOKENS = 800
SEED = 0
TOP_K = 3
THRESHOLD = 0.05
ROUNDS = 1
DEEPSEEK_MODEL = "deepseek-chat"

DATASETS = {
    "mmlu": {
        "file": "data/test/MMLU_sampled_test.json", "mode": "mc", "num_choice": 4,
        "gen_data": "MMLU_sampled", "subset": 200, "sample": True,
    },
    "mmlu_pro": {
        "file": "data/test/MMLU_Pro_sampled_test.json", "mode": "mc", "num_choice": 10,
        "gen_data": "MMLU_Pro_sampled", "subset": 200, "sample": True,
    },
    "math": {
        "file": "data/test/MATH_test.json", "mode": "math", "num_choice": 0,
        "gen_data": "MATH", "subset": 100, "sample": True,
    },
    "medmcqa": {
        "file": "data/test/MedMCQA_sampled_test.json", "mode": "mc", "num_choice": 4,
        "gen_data": "MedMCQA_sampled", "subset": 100, "sample": False,
    },
    "humaneval": {
        "file": "data/dev/human_eval_dev.json", "mode": "code", "num_choice": 0,
        "gen_data": "human_eval", "subset": 50, "sample": False,
    },
}


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


def _sanitize(obj):
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


def build_instruction(item, mode, num_choice):
    if mode == "code":
        return (
            "Given the following Python function signature, complete the function "
            "to match the expected behavior.\n\n"
            f"{item['prompt']}\n\n"
            "Completed Function:"
        )
    q = item["question"]
    if mode == "math":
        return (
            f"Question: {q}\n"
            "Provide your step-by-step reasoning first, and then print "
            '"The answer is \\boxed{X}", where X is the final answer, at the end of '
            "your response."
        )
    return (
        f"Question: {q}\n"
        "Provide your step-by-step reasoning first, and then print "
        '"The answer is (x)", where x is the answer choice (one capital letter), '
        "at the end of your response."
    )


def build_final_prompt(mode):
    if mode == "math":
        return ('Please conclude by printing "The answer is \\boxed{X}", where X is '
                "the final answer, at the end of your response.")
    if mode == "code":
        return ""
    return ('Please conclude by printing "The answer is (x)", where x is the answer '
            "choice (one capital letter), at the end of your response.")


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


def _call_deepseek_json(prompt, max_tokens=1500, retries=3):
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
            print(f"  [deepseek judge] failed ({attempt + 1}): {e}")
            time.sleep(5 + attempt * 4)
    return "", "error"


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


def _parse_winner(raw):
    if not raw:
        return None
    parsed = _parse_json_loose(raw)
    if parsed and parsed.get("winner"):
        mm = re.search(r"M([0-9])", str(parsed["winner"]))
        return int(mm.group(1)) if mm else None
    return None


def evidence_prompt(question, chain):
    return (
        "You are in a guided review of a problem.\n\n"
        f"###Problem:\n{question}\n\n"
        f"###Your current solution/reasoning:\n\"\"\"{chain}\"\"\"\n\n"
        "###Task:\n"
        "Give INDEPENDENT evidence supporting YOUR conclusion. Do NOT refer to other "
        "models' answers or reasoning.\n"
        "1. data: the concrete facts/numbers/steps from the problem that support "
        "your conclusion\n"
        "2. warrant: why these data imply your conclusion (the reasoning link)\n"
        "3. backing: the conditions under which your rule/approach holds\n"
        "4. rebuttal: how you rule out the main alternative answer/solution\n"
        'Then restate your final answer at the end ("The answer is (X)" for '
        "multiple-choice, or the final expression/result, or the completed code)."
    )


def verdict_prompt(question, chains, evidences, names):
    blocks = "\n\n".join(
        f"M{i} ({names[i]}) ORIGINAL solution/reasoning:\n\"\"\"{chains[i][:2200]}\"\"\"\n"
        f"M{i} NEW evidence:\n\"\"\"{evidences.get(i, '(none)')}\"\"\""
        for i in range(len(chains))
    )
    return (
        "You are an impartial adjudicator for a problem. Several models each produced "
        "a solution, then each provided NEW independent evidence for their own "
        "solution.\n\n"
        "Your task: decide which model's solution + evidence is most credible.\n"
        "Rules:\n"
        "1. Judge ONLY whether the evidence is relevant to the problem, internally "
        "coherent, and actually supports that model's own conclusion.\n"
        "2. IGNORE answer length, confidence_level, and confident wording.\n"
        "3. Never mention the true answer; you do not have it.\n"
        "4. If one model's evidence is self-contradictory or contradicts the problem, "
        "do not choose it.\n\n"
        f"###Problem:\n{question}\n\n"
        f"###Solutions and new evidence:\n{blocks}\n\n"
        'Output STRICT JSON: {"winner": "M0" or "M1" or "M2", '
        '"reason": "<2-3 sentences>", "confidence": <0-1>}'
    )


def _safe_letter(text, num_choice):
    if not text:
        return None
    v = get_alphabet_choice(str(text), num_choice=num_choice)
    return None if v in (None, "", "N/A") else v


def _math_ans_from_chain(chain):
    """Robust final-answer extraction for MATH chains.

    Priority: LAST JSON "answer" value (what the model itself declared) ->
    last \\boxed{...} -> last "the answer is ...".  Never returns the whole
    raw chain (the old bug that made correct winners look wrong).
    """
    if not chain:
        return None
    for raw_v in reversed(re.findall(
            r'"answer"\s*:\s*("(?:[^"\\]|\\.)*"|[^,}\n\]]+)', chain)):
        v = raw_v.strip()
        if v.startswith('"') and v.endswith('"'):
            try:
                v = json.loads(v)
            except Exception:
                v = v[1:-1]
        if isinstance(v, dict):
            xs = [v.get(k) for k in ("x", "y") if k in v]
            v = "(" + ",".join(str(x) for x in xs) + ")" if xs else str(v)
        v = str(v).strip()
        if v and v.lower() not in ("n/a", "none") and len(v) <= 80:
            return v
    boxed = re.findall(r"\\boxed\{([^{}]*)\}", chain)
    if boxed:
        return boxed[-1].strip()
    said = re.findall(r"[Tt]he answer is\s*[:\s]*\(?\$?([^\.\n\$]+)", chain)
    if said:
        return said[-1].strip()
    return None


def _check_humaneval(problem, completion, timeout=8):
    """Run unit tests for one HumanEval dev item on a completion."""
    if not completion:
        return False
    source = (
        problem["prompt"] + "\n" + completion + "\n\n" +
        problem["test"] + "\n" +
        f"check({problem['entry_point']})"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", source],
            capture_output=True, text=True, timeout=timeout,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _run_baseline_orig(models_dict_unique, model_name_idx, initial_responses, instruction,
                       final_prompt, mode, num_choice, meta_cfg):
    """Exact GoA_orig body: mutual edge sampling + message passing + mean pooling."""
    output = edge_sampling(
        models_dict=models_dict_unique,
        model_name_idx=model_name_idx,
        initial_responses=initial_responses,
        messages=[instruction],
        threshold=THRESHOLD,
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        seed=SEED,
        confidences=None,
    )
    final_response = None
    score_dict = {}
    note = "goa"
    if not isinstance(output, tuple):
        if output == -1:
            note = "fallback_mean"
            final_response, _, _ = graph_pooling(
                model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
                refined_response=initial_responses, messages=[instruction],
                temperature=TEMP, max_tokens=MAX_TOKENS,
                final_prompt=final_prompt, seed=SEED,
            )
        else:
            note = "single_node"
            final_response = output
    else:
        source_edges, target_edges, score_dict, _sm, _fb, _fbe, _it, _ot = output
        round_responses = deepcopy(initial_responses)
        try:
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
                    round=f"{_round + 1}/{ROUNDS}",
                    final_prompt=final_prompt,
                    seed=SEED,
                )
                round_responses = deepcopy(t2s)
            final_response, _, _ = graph_pooling(
                model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
                refined_response=round_responses, weights=score_dict,
                messages=[instruction], temperature=TEMP, max_tokens=MAX_TOKENS,
                final_prompt=final_prompt, seed=SEED,
            )
        except Exception as e:
            final_response = ""
            note = f"error:{e}"
    if final_response is None:
        final_response = ""
    return final_response, score_dict, note


def _run_j(question, chains, initial_answers, names, models_dict_unique,
           model_name_idx, mode, num_choice):
    """DeepSeek judge-led closed loop. Returns (winner_i, J_answer_raw, note, evidence)."""
    if len(chains) < 2:
        return None, None, "single_node_skip", {}
    evidences = {}
    for i in range(len(chains)):
        un = model_name_idx[i]
        cfg = models_dict_unique[un]
        out = _call(cfg["model_id"], cfg["url"],
                    evidence_prompt(question, chains[i]),
                    max_tokens=800, temperature=TEMP,
                    debug_txt=f"[J evidence {un}] ")
        evidences[i] = out
    raw, status = _call_deepseek_json(
        verdict_prompt(question, chains, evidences, list(model_name_idx.values())),
        max_tokens=1200, retries=3,
    )
    wi = _parse_winner(raw)
    if wi is None or wi not in range(len(chains)):
        return None, None, f"verdict_parse_fail:{status}", evidences
    ans = initial_answers.get(wi)
    return wi, ans, "adjudicated", evidences


def process_one(args):
    ds, item, cfg, meta_cfg, models_dict = args
    mode = cfg["mode"]
    num_choice = cfg["num_choice"]
    gen_data = cfg["gen_data"]
    t0 = time.time()

    instruction = build_instruction(item, mode, num_choice)
    final_prompt = build_final_prompt(mode)

    sampled_nodes, _fb, _it, _ot = node_sampling_model_card(
        model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
        messages=[instruction], model_info_dict=models_dict,
        top_k=TOP_K, temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
    )
    unique_names, unique_to_original = make_unique_node_names(sampled_nodes)
    models_dict_unique = {un: models_dict[unique_to_original[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    initial_responses, confidences, initial_answers = {}, {}, {}
    for i, un in enumerate(unique_names):
        raw, ans, conf, _it, _ot = generate_initial_response_with_confidence(
            model_id=models_dict_unique[un]["model_id"],
            endpoint=models_dict_unique[un]["url"],
            instruction=instruction, data=gen_data, num_choice=num_choice,
            temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
            debug_txt=f"[Initial {un}] ",
        )
        initial_responses[i] = raw
        confidences[i] = conf
        if mode == "mc":
            initial_answers[i] = _safe_letter(ans if ans is not None else raw, num_choice)
        elif mode == "math":
            initial_answers[i] = (_math_ans_from_chain(raw)
                                  or (str(ans).strip() if ans not in (None, "N/A") else None))
        else:
            # Always clean code answers: strip markdown fences / JSON wrappers.
            initial_answers[i] = extract_human_eval_completion(
                str(ans) if ans not in (None, "N/A", "") else raw)

    # Confidence replacement (original GoA_orig behaviour)
    general_model_name = META
    for i in range(len(unique_names)):
        try:
            replaced, _it, _ot = maybe_replace_with_general(
                node_idx=i, node_name=unique_to_original[unique_names[i]],
                confidence=confidences[i], models_dict=models_dict,
                general_model_name=general_model_name,
                initial_responses=initial_responses, confidences=confidences,
                answers=initial_answers, sampled_nodes=sampled_nodes,
                instruction=instruction, data=gen_data, num_choice=num_choice,
                temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
            )
            if replaced:
                unique_names[i] = general_model_name if unique_names.count(general_model_name) == 0 \
                    else f"{general_model_name}_{i}"
                unique_to_original[unique_names[i]] = general_model_name
        except Exception as e:
            print(f"[{ds} {item.get('idx')}] replacement error {e}", flush=True)
    model_name_idx = dict(enumerate(unique_names))
    models_dict_unique = {un: models_dict[unique_to_original[un]] for un in unique_names}

    # ---------------- Branch A: original mutual-eval pipeline ----------------
    a_res, score_dict, a_note = "", {}, "error"
    try:
        a_res, score_dict, a_note = _run_baseline_orig(
            models_dict_unique, model_name_idx, initial_responses, instruction,
            final_prompt, mode, num_choice, meta_cfg,
        )
    except Exception as e:
        a_note = f"error:{e}"
    if mode == "mc":
        a_answer = _safe_letter(a_res, num_choice)
    elif mode == "math":
        a_answer = _math_ans_from_chain(a_res)
    else:
        a_answer = extract_human_eval_completion(a_res)

    # ---------------- Branch J: evidence + DeepSeek adjudication ----------------
    question = item["prompt"] if mode == "code" else item["question"]
    chains = {int(k): v for k, v in initial_responses.items()}
    j_winner, j_answer, j_note, evidences = _run_j(
        question, chains, initial_answers, model_name_idx,
        models_dict_unique, model_name_idx, mode, num_choice,
    )

    result = {
        "idx": item.get("idx"),
        "gold": item.get("gold_answer"),
        "ds": ds,
        "sampled_nodes": sampled_nodes,
        "unique_names": unique_names,
        "initial_answers": _sanitize(initial_answers),
        "initial_responses": _sanitize(initial_responses),
        "A_answer": a_answer,
        "A_note": a_note,
        "A_score_dict": _sanitize(score_dict),
        "J_winner": j_winner,
        "J_answer": j_answer,
        "J_note": j_note,
    }
    if mode == "code":
        result["A_pass"] = _check_humaneval(item, a_answer)
        result["J_pass"] = _check_humaneval(item, j_answer)
    else:
        gold = str(item.get("gold_answer", "")).strip()
        if mode == "mc":
            result["A_correct"] = (a_answer == gold)
            result["J_correct"] = (j_answer == gold)
        else:
            try:
                result["A_correct"] = bool(is_math_equiv(str(a_answer or ""), gold))
            except Exception:
                result["A_correct"] = False
            try:
                result["J_correct"] = bool(is_math_equiv(str(j_answer or ""), gold))
            except Exception:
                result["J_correct"] = False
        result["gold_in_pool"] = any(
            (str(v) == gold) for v in initial_answers.values() if v not in (None, "")
        )
    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{ds} idx={item.get('idx')}] {round(result['time_s'], 1)}s | "
          f"A={'ok' if result.get('A_correct', result.get('A_pass')) else 'X'} "
          f"J={'ok' if result.get('J_correct', result.get('J_pass')) else 'X'} "
          f"note={a_note}/{j_note}", flush=True)
    return result


def _mcnemar_exact_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(DATASETS.keys()))
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--subset_seed", type=int, default=0)
    ap.add_argument("--idxs_path", default="")
    args = ap.parse_args()

    cfg = DATASETS[args.dataset]
    if not os.path.exists(cfg["file"]):
        cfg["file"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), cfg["file"])
    raw = json.load(open(cfg["file"]))
    n = len(raw)
    if args.idxs_path:
        idxs = json.load(open(args.idxs_path))
    elif cfg["sample"] and args.limit <= 0:
        idxs = sorted(random.Random(args.subset_seed).sample(range(n), min(cfg["subset"], n)))
    else:
        idxs = list(range(n))
    if args.limit:
        idxs = idxs[:args.limit]
    items = [dict(raw[i], idx=i) for i in idxs]
    print(f"[Paired-{args.dataset}] items={len(items)} subset_of={n}", flush=True)
    with open(args.out + ".idxs.json", "w") as f:
        json.dump(idxs, f)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("WARNING: DEEPSEEK_API_KEY not set; J will fail.", flush=True)

    meta_cfg = model_endpoint_dict[META]
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    task_args = [(args.dataset, it, cfg, meta_cfg, models_dict) for it in items]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_one, ta): ta[1]["idx"] for ta in task_args}
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
            print(f"[Paired-{args.dataset}] progress {done}/{len(task_args)}", flush=True)

    results.sort(key=lambda r: r["idx"])
    with open(args.out, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    key = "pass" if cfg["mode"] == "code" else "correct"
    a_ok = sum(1 for r in results if r.get(f"A_{key}"))
    j_ok = sum(1 for r in results if r.get(f"J_{key}"))
    fixed = sum(1 for r in results if not r.get(f"A_{key}") and r.get(f"J_{key}"))
    broken = sum(1 for r in results if r.get(f"A_{key}") and not r.get(f"J_{key}"))
    p = _mcnemar_exact_p(fixed, broken)
    print("=" * 70, flush=True)
    print(f"[Paired-{args.dataset}] n={len(results)} "
          f"A_orig={a_ok} ({a_ok / max(len(results), 1):.2%}) | "
          f"J={j_ok} ({j_ok / max(len(results), 1):.2%})", flush=True)
    print(f"[Paired-{args.dataset}] fixed={fixed} broken={broken} "
          f"same={len(results) - fixed - broken} McNemar p={p:.4g}", flush=True)
    print(f"[Paired-{args.dataset}] saved -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
