# -*- coding: utf-8 -*-
"""
P0-3 / P1 v1: Judge-led evidence interrogation + adjudication closed loop.

Per-question protocol (advisor 5-point design):
  1. NO direct model-to-model exchange. Judge collects all information.
  2. Divergence/conflict identification (DeepSeek, reuse identify_divergence).
  3. Each participant is asked ONE unbiased question for NEW evidence supporting
     its OWN conclusion (data / warrant / rebuttal), no cross-references
     (evidence_prompt; Mercer/Berkowitz & Gibbs style independent reasoning).
  4. Judge (DeepSeek) ADJUDICATES: reads question + original chains + new evidence,
     outputs one winner chain. Verdict criteria forbid length/confidence heuristics:
     only consistency with question facts and internal coherence of the evidence.
  5. Verdict -> final answer letter of the winner chain (判定直接决定，提问不改权重；
     weight change tracked separately in a later variant).

Evaluation rule (offline, gold only for filtering/layering, never fed to judge):
  gold letter in pool -> use J; otherwise -> keep stored baseline A.
"""

import json
import os
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from teacher_validation import (
    make_unique_node_names,
    identify_divergence,
    evidence_prompt,
    _call,
    _extract_letter,
    _parse_json_loose,
    _sanitize,
    _call_deepseek_json,
    REF_MODELS,
    TEMP,
    MAX_TOKENS,
    make_instruction,
)


def _verdict_prompt(question, chains, evidences, names):
    blocks = "\n\n".join(
        f"M{i} ({names[i]}) ORIGINAL chain:\n\"\"\"{chains[i][:1800]}\"\"\"\n"
        f"M{i} NEW evidence:\n\"\"\"{evidences.get(i, '(none)')}\"\"\""
        for i in range(len(chains))
    )
    return (
        "You are an impartial adjudicator for a graduate-level science multiple-choice "
        "question. Three models each gave a reasoning chain, then each provided NEW "
        "independent evidence for their own conclusion.\n\n"
        "Your task: decide which model's reasoning + evidence is most credible.\n"
        "Rules:\n"
        "1. Judge ONLY: whether the evidence uses facts from the question, is internally "
        "coherent, and actually supports that model's conclusion.\n"
        "2. IGNORE answer length, confidence_level, and how confident the wording sounds.\n"
        "3. Never mention the true answer; you do not have it.\n"
        "4. If one model's evidence is self-contradictory or contradicts the question, "
        "do not choose it.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Chains and new evidence:\n{blocks}\n\n"
        'Output STRICT JSON: {"winner": "M0" or "M1" or "M2", '
        '"reason": "<2-3 sentences>", "confidence": <0-1>}'
    )


def _prometheus_verdict_prompt(question, chains, evidences, names):
    """Prometheus-native style: prose feedback + a terminal [WINNER] marker."""
    blocks = "\n\n".join(
        f"M{i} ({names[i]}) ORIGINAL chain:\n\"\"\"{chains[i][:1800]}\"\"\"\n"
        f"M{i} NEW evidence:\n\"\"\"{evidences.get(i, '(none)')}\"\"\""
        for i in range(len(chains))
    )
    return (
        "###Task Description:\n"
        "Three models (M0, M1, M2) answered a graduate-level science multiple-choice "
        "question and each provided NEW independent evidence for its own conclusion. "
        "Judge which model's reasoning + evidence is most credible.\n"
        "Rules:\n"
        "1. Judge ONLY whether the evidence uses facts from the question, is internally "
        "coherent, and supports that model's own conclusion.\n"
        "2. IGNORE answer length, confidence_level, and confident wording.\n"
        "3. Never mention the true answer; you do not have it.\n"
        "4. If a model's evidence is self-contradictory or contradicts the question, "
        "do not choose it.\n"
        "5. Give 2-3 sentences of feedback, then end with exactly one line:\n"
        '   [WINNER] M0   (or M1 / M2)\n\n'
        f"###Question:\n{question}\n\n"
        f"###Chains and new evidence:\n{blocks}\n\n"
        "###Feedback and [WINNER]:\n"
    )


def _abstain_prompt(question, chains, evidences, names, round_label):
    """Prometheus-style adjudication with ABSTAIN option + [WINNER]/[CONF] markers."""
    blocks = "\n\n".join(
        f"M{i} ({names[i]}) ORIGINAL chain:\n\"\"\"{chains[i][:1800]}\"\"\"\n"
        f"M{i} {round_label} evidence:\n\"\"\"{evidences.get(i, '(none)')}\"\"\""
        for i in range(len(chains))
    )
    return (
        "###Task Description:\n"
        "Three models (M0, M1, M2) answered a graduate-level science multiple-choice "
        "question, and each provided NEW independent evidence for its own conclusion.\n"
        "Judge which model's reasoning + evidence is most credible.\n"
        "Rules:\n"
        "1. Judge ONLY whether the evidence uses facts from the question, is internally "
        "coherent, and supports that model's own conclusion.\n"
        "2. IGNORE answer length, confidence_level, and confident wording.\n"
        "3. Never mention the true answer; you do not have it.\n"
        "4. If a model's evidence is self-contradictory or contradicts the question, "
        "do not choose it.\n"
        "5. ABSTAIN (winner = none) if no model clearly wins: all evidence is weak, "
        "two models are tied, or the evidence is insufficient to decide.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Chains and evidence:\n{blocks}\n\n"
        "End with exactly two lines:\n"
        "[WINNER] M0  (or M1 / M2 / none)\n"
        "[CONF] 0.0-1.0  (use a low value when abstaining)\n"
        "###Output:\n"
    )


def _deepen_prompt(question, chain, first_evidence):
    return (
        "You are in a SECOND round of a science multiple-choice question review.\n\n"
        f"###Question:\n{question}\n\n"
        f"###Your reasoning:\n\"\"\"{chain}\"\"\"\n\n"
        f"###Your first-round evidence:\n\"\"\"{first_evidence}\"\"\"\n\n"
        "###Task (second round, more demanding):\n"
        "1. Check every number, reagent, condition and qualifier in your conclusion "
        "against the question text; explicitly correct any mismatch.\n"
        "2. Add ONE key fact or calculation from the question you did not mention before.\n"
        "3. Explicitly rule out ONE alternative answer you have not yet excluded.\n"
        "Then restate your final answer: \"The answer is (X)\"."
    )


def _parse_abstain(raw):
    """Parse [WINNER] M0/M1/M2/none and [CONF] x.xx from raw text."""
    import re
    if not raw:
        return None, None, "no_raw"
    mw = re.search(r"\[WINNER\]\s*(M[0-9]|none)", raw, re.I)
    mc = re.search(r"\[CONF\]\s*([0-9]+(?:\.[0-9]+)?)", raw)
    winner = mw.group(1).upper() if mw else None
    conf = float(mc.group(1)) if mc else None
    mode = "markers" if (mw or mc) else "no_markers"
    return winner, conf, mode


def _adjudicate(judge, question, chains, evidences, names):
    """One adjudication call. judge in {deepseek, prometheus, qwen}."""
    if judge == "deepseek":
        prompt = _verdict_prompt(question, chains, evidences, names)
        raw, status = _call_deepseek_json(prompt, max_tokens=1200, retries=3)
        return raw, status
    # 7B vLLM adjudicators (same scale as answering models)
    if judge == "prometheus":
        cfg = model_endpoint_dict["prometheus"]
        prompt = _prometheus_verdict_prompt(question, chains, evidences, names)
    elif judge == "qwen":
        cfg = model_endpoint_dict["qwen"]
        prompt = _verdict_prompt(question, chains, evidences, names)
    else:
        raise ValueError(f"unknown judge: {judge}")
    raw = _call(cfg["model_id"], cfg["url"], prompt,
                max_tokens=800, temperature=0.2,
                debug_txt=f"[Adjudicate {judge}] ")
    return raw, "ok"


def _extract_winner(raw, judge):
    """JSON first; then prometheus-native [WINNER] / prose patterns."""
    if not raw:
        return None
    parsed = _parse_json_loose(raw)
    if parsed and parsed.get("winner"):
        return parsed, "json"
    import re
    m = re.search(r"\[WINNER\]\s*M(\d)", raw)
    if m:
        return {"winner": f"M{m.group(1)}"}, "winner_marker"
    # prose fallback: M index described as most credible/coherent/correct
    pats = [
        r"M(\d)[^.]{0,60}?(?:more credible|more coherent|most credible|most coherent|better supported|is the strongest|wins)",
        r"(?:more credible|more coherent|most credible|most coherent|better supported|wins)[^.]{0,40}?M(\d)",
    ]
    for p in pats:
        mm = re.search(p, raw, re.I)
        if mm:
            g = mm.group(1) if mm.group(1) else mm.group(2)
            return {"winner": f"M{g}"}, "prose"
    # any first M index that is praised
    mm = re.search(r"M(\d)[^.]{0,50}?(?:coherent|credible|correct|consistent|supported)", raw, re.I)
    if mm:
        return {"winner": f"M{mm.group(1)}"}, "prose_loose"
    return None, "no_match"


def run_one(rec, qmap, force_all=False, judge="deepseek"):
    idx = rec["idx"]
    gold = rec["gold"]
    question = qmap[idx]
    instruction = make_instruction(question)
    result = {
        "idx": idx, "gold": gold,
        "stored_A": (rec.get("A") or {}).get("answer"),
        "stored_weights": (rec.get("A") or {}).get("score_dict"),
        "vetoed": rec.get("vetoed"),
    }
    t0 = time.time()

    unique_names = rec["unique_names"]
    chains = {int(k): v for k, v in rec["initial_responses"].items()}
    initial_answers = {int(k): v for k, v in (rec.get("initial_answers") or {}).items()}
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    _u, u_to_orig = make_unique_node_names(rec["sampled_nodes"])
    models_dict_unique = {un: models_dict[u_to_orig[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    gold_in_pool = gold in [v for v in initial_answers.values() if v and v != "N/A"]
    result["gold_in_pool"] = gold_in_pool
    result["initial_answers"] = initial_answers

    if (not gold_in_pool) and (not force_all):
        # P1 rule: closed loop only on pool-correct questions; others keep baseline
        result["J_answer"] = result["stored_A"]
        result["note"] = "baseline_keep_no_gold_in_pool"
        result["time_s"] = round(time.time() - t0, 1)
        return result
    if force_all and (not gold_in_pool):
        result["note_prefix"] = "force_all_no_gold_in_pool"

    try:
        # step 1-2: divergence (informational only). Skip when a 7B judge is used
        # so the whole pipeline stays DeepSeek-free.
        result["divergence_source"] = "skipped_7b_pipeline"

        # step 3: one unbiased NEW-evidence question per participant
        evidences = {}
        for i in range(len(chains)):
            un = model_name_idx[i]
            node_cfg = models_dict_unique[un]
            out = _call(node_cfg["model_id"], node_cfg["url"],
                        evidence_prompt(question, chains[i]),
                        max_tokens=MAX_TOKENS, temperature=TEMP,
                        debug_txt=f"[Adjudicate evidence {un}] ")
            evidences[i] = out
        result["evidences"] = evidences

        # step 4: adjudication by configured judge (deepseek | prometheus | qwen)
        raw, status = _adjudicate(judge, question, chains, evidences, unique_names)
        vd, parse_mode = _extract_winner(raw, judge)
        result["verdict_raw"] = raw
        result["verdict_status"] = status
        result["parse_mode"] = parse_mode
        if vd and vd.get("winner"):
            w = str(vd["winner"]).upper()
            m = re_match_w = None
            import re
            mm = re.search(r"M([0-9])", w)
            wi = int(mm.group(1)) if mm else None
            result["verdict"] = vd
            if wi is not None and wi in chains:
                result["J_answer"] = initial_answers.get(wi)
                result["winner_node"] = wi
                result["winner_model"] = unique_names[wi]
                result["note"] = "adjudicated"
            else:
                result["J_answer"] = None
                result["note"] = f"bad_winner:{w}"
        else:
            result["verdict"] = vd
            result["J_answer"] = None
            result["note"] = "verdict_parse_fail"
    except Exception as e:
        result["J_answer"] = None
        result["note"] = f"error:{e}"
        print(f"[{idx}] error: {e}", flush=True)

    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{idx}] done {result['time_s']}s | gold={gold} gold_in_pool={gold_in_pool} "
          f"A={result['stored_A']} J={result.get('J_answer')} note={result.get('note')}", flush=True)
    return result


def run_two_round(rec, qmap):
    """Version B (advisor style): round-1 adjudication with abstain+confidence;
    if not confident, ask a SECOND round of targeted evidence, re-adjudicate;
    if still no clear winner -> abstain -> keep stored baseline A.
    Both rounds are always recorded so thresholds can be scanned offline."""
    idx = rec["idx"]
    gold = rec["gold"]
    question = qmap[idx]
    instruction = make_instruction(question)
    result = {
        "idx": idx, "gold": gold,
        "stored_A": (rec.get("A") or {}).get("answer"),
        "stored_weights": (rec.get("A") or {}).get("score_dict"),
        "vetoed": rec.get("vetoed"),
    }
    t0 = time.time()

    unique_names = rec["unique_names"]
    chains = {int(k): v for k, v in rec["initial_responses"].items()}
    initial_answers = {int(k): v for k, v in (rec.get("initial_answers") or {}).items()}
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    _u, u_to_orig = make_unique_node_names(rec["sampled_nodes"])
    models_dict_unique = {un: models_dict[u_to_orig[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    gold_in_pool = gold in [v for v in initial_answers.values() if v and v != "N/A"]
    result["gold_in_pool"] = gold_in_pool
    result["initial_answers"] = initial_answers

    if not gold_in_pool:
        result["J_answer"] = result["stored_A"]
        result["note"] = "baseline_keep_no_gold_in_pool"
        result["time_s"] = round(time.time() - t0, 1)
        return result

    def ask_evidence(prompt_fn, prev=None):
        ev = {}
        for i in range(len(chains)):
            un = model_name_idx[i]
            node_cfg = models_dict_unique[un]
            if prev is not None:
                p = prompt_fn(question, chains[i], prev.get(i, ""))
            else:
                p = prompt_fn(question, chains[i])
            ev[i] = _call(node_cfg["model_id"], node_cfg["url"], p,
                          max_tokens=MAX_TOKENS, temperature=TEMP,
                          debug_txt=f"[TwoRound ev {un}] ")
        return ev

    def adjudicate(evidences, label):
        prompt = _abstain_prompt(question, chains, evidences, unique_names, label)
        cfg = model_endpoint_dict["prometheus"]
        raw = _call(cfg["model_id"], cfg["url"], prompt,
                    max_tokens=900, temperature=0.2,
                    debug_txt=f"[TwoRound adj {label}] ")
        winner, conf, mode = _parse_abstain(raw)
        return {"winner": winner, "conf": conf, "mode": mode, "raw": raw}

    try:
        # round 1
        ev1 = ask_evidence(evidence_prompt)
        r1 = adjudicate(ev1, "first")
        result["evidence1"] = ev1
        result["round1"] = {k: r1[k] for k in ("winner", "conf", "mode")}
        result["round1_raw"] = r1["raw"]

        # round 2 always recorded for offline threshold scan
        ev2 = ask_evidence(_deepen_prompt, prev=ev1)
        r2 = adjudicate({i: ev1.get(i, "") + "\n\n[second round]\n" + ev2.get(i, "")
                         for i in range(len(chains))}, "second")
        result["evidence2"] = ev2
        result["round2"] = {k: r2[k] for k in ("winner", "conf", "mode")}
        result["round2_raw"] = r2["raw"]

        # default resolution: conf1>=0.7 -> r1; conf2>=0.5 -> r2; else baseline
        def letter_of(w):
            if not w or w == "NONE":
                return None
            import re
            m = re.match(r"M(\d)", w)
            return initial_answers.get(int(m.group(1))) if m else None

        c1 = r1["conf"] if r1["conf"] is not None else 0.0
        c2 = r2["conf"] if r2["conf"] is not None else 0.0
        if r1["winner"] and r1["winner"] != "NONE" and c1 >= 0.7:
            ans = letter_of(r1["winner"]); src = "r1"
        elif r2["winner"] and r2["winner"] != "NONE" and c2 >= 0.5:
            ans = letter_of(r2["winner"]); src = "r2"
        else:
            ans = result["stored_A"]; src = "abstain_baseline"
        result["J_answer"] = ans
        result["resolve"] = src
        result["note"] = "two_round"
    except Exception as e:
        result["J_answer"] = None
        result["note"] = f"error:{e}"
        print(f"[{idx}] error: {e}", flush=True)

    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{idx}] done {result['time_s']}s | gold={gold} A={result['stored_A']} "
          f"J={result.get('J_answer')} resolve={result.get('resolve')}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--full_results", default="outputs/hard_full_198.json")
    ap.add_argument("--idxs_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force_all", action="store_true",
                    help="adjudicate every question (no gold-in-pool filter)")
    ap.add_argument("--judge", default="deepseek", choices=["deepseek", "prometheus", "qwen"])
    ap.add_argument("--mode", default="single", choices=["single", "two_round"])
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    qmap = {i: s["question"] for i, s in enumerate(samples)}
    with open(args.idxs_path) as f:
        idxs = json.load(f)
    with open(args.full_results) as f:
        records = json.load(f)
    recs = [r for r in records if r["idx"] in idxs]
    print(f"[Adjudicate] questions: {len(recs)}", flush=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        if args.mode == "two_round":
            futs = {ex.submit(run_two_round, rec, qmap): rec["idx"] for rec in recs}
        else:
            futs = {ex.submit(run_one, rec, qmap, args.force_all, args.judge): rec["idx"] for rec in recs}
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
            print(f"[Adjudicate] progress {done}/{len(recs)}", flush=True)
    print(f"[Adjudicate] saved {len(results)} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
