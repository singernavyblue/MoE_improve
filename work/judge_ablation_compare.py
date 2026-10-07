# -*- coding: utf-8 -*-
"""Judge ablation on 40 fixed chains: 4-dim pairwise rubric with Prometheus-7B (server)
vs a strong LLM API. Run on the server. Usage:
    python judge_ablation_compare.py --judge prometheus
    python judge_ablation_compare.py --judge strong --base-url ... --api-key ... --model ...
Output: per-question per-node margin scores -> top chain correctness, saved as JSON.
"""
import argparse
import json
import sys
import time

sys.path.insert(0, "/root/GoA")

RUBRIC_4DIM = (
    "Score each reasoning chain on four independent dimensions, 1 (worst) to 5 (best).\n"
    "\n"
    "D1 Goal Alignment (gate dimension):\n"
    "5: correctly identifies the question type (calculation/judgment/except/structure) "
    "and respects every qualifier.\n"
    "4: understands the question but misses one minor qualifier.\n"
    "3: understands the question type but substitutes the goal midway (e.g., switches "
    "from 'find the correct route' to 'find the closest option').\n"
    "2: answers a related but different question (e.g., asked for the structure of "
    "product 4 but only argues the starting configuration).\n"
    "1: inverts the question type (e.g., an 'except' question answered with the wrong "
    "item) or answers a different question.\n"
    "\n"
    "D2 Information Utilization (domain knowledge / given conditions / options):\n"
    "5: every chemical/physical/biological fact is correct, all given numbers and "
    "conditions are used, and options are checked one by one.\n"
    "4: facts are mostly correct; one non-critical condition or option is missed.\n"
    "3: conclusion is correct but the reasoning contains a substantive factual error "
    "(errors that cancel out).\n"
    "2: invokes a wrong key fact/reagent/property, which drives the wrong conclusion.\n"
    "1: basically ignores the given information or fabricates facts.\n"
    "\n"
    "D3 Result Verification (consistency check before committing):\n"
    "5: performs an explicit consistency check: conclusion vs reasoning, conclusion "
    "vs options, numbers vs question.\n"
    "4: reasoning and conclusion are consistent but no explicit check is performed.\n"
    "3: second-guesses or revises itself but does not fully verify; final conclusion "
    "is consistent with the reasoning.\n"
    "2: the conclusion directly contradicts the chain's own reasoning and the model "
    "does not notice.\n"
    "1: no verification at all; conclusion asserted without support, or an obviously "
    "impossible result given confidently.\n"
    "\n"
    "D4 Efficiency (redundancy only; short-but-wrong is as wrong as long-but-wrong):\n"
    "5: direct, complete, no filler; every sentence advances the reasoning.\n"
    "4: minor redundancy that does not hurt understanding.\n"
    "3: one or two repeated arguments or non-progress paragraphs.\n"
    "2: many detours: restating the question, restarting repeatedly, padding length "
    "to fake rigor.\n"
    "1: pure restatement of the question with no content, or a badly corrupted output.\n"
    "\n"
    "Rules:\n"
    "- Score each dimension independently; do NOT give all four dimensions the same "
    "score because of one overall impression (anti-halo).\n"
    "- Length and confidence are NOT correctness.\n"
    "- A chain scoring 1-2 on Goal Alignment cannot score above 2 overall.\n"
    "- Then compare the two chains dimension by dimension, prioritizing D1, then D3, "
    "then D2, then D4, and decide which chain is better."
)

REFERENCE_LINE = "No reference answer is provided. Evaluate the two responses on their own merits."
MARGIN_MAP = {"clearly better": 0.85, "better": 0.70, "slightly better": 0.60, "comparable": 0.50}


def build_prompt(question, resp_a, resp_b):
    return (
        "###Task Description:\n"
        "An instruction (might include an Input inside it), two responses to "
        "evaluate (denoted as Response A and Response B), and an evaluation "
        "criteria are given.\n"
        "1. Write a detailed feedback that assesses the quality of the two "
        "responses strictly based on the given evaluation criteria, not "
        "evaluating in general.\n"
        "1b. Score Response A and Response B on each of the four dimensions "
        "D1-D4 (1-5), writing the per-dimension scores explicitly in your "
        "feedback.\n"
        "2. Make comparisons between Response A and Response B. Go straight "
        "to the point and mention the commonalities and differences between them.\n"
        "3. After writing the feedback, indicate the better response: \"A\", "
        "\"B\", or \"tie\" if they are of comparable quality.\n"
        "4. Also indicate the strength of your preference: \"clearly better\", "
        "\"better\", \"slightly better\", or \"comparable\".\n"
        "5. The output format should look as follows: \"Feedback: (write a "
        "feedback for criteria) [RESULT] (A, B, or tie) [PREFERENCE] (clearly "
        "better, better, slightly better, or comparable)\"\n"
        "6. Please do not generate any other opening, closing, and explanations.\n\n"
        "###Instruction:\n"
        f"{question}\n\n"
        "###Response A:\n"
        f"{resp_a}\n\n"
        "###Response B:\n"
        f"{resp_b}\n\n"
        "###Reference Answer:\n"
        f"{REFERENCE_LINE}\n\n"
        "###Score Rubric:\n"
        f"{RUBRIC_4DIM}\n\n"
        "###Feedback:\n"
    )


def parse_margin(text):
    """Extract [RESULT] and [PREFERENCE]; return (winner, margin) or (None, None)."""
    import re
    m = re.search(r"\[RESULT\]\s*(A|B|tie)", text, re.I)
    if not m:
        return None, None
    winner = m.group(1).lower()
    p = re.search(r"\[PREFERENCE\]\s*(clearly better|better|slightly better|comparable)", text, re.I)
    margin = MARGIN_MAP.get(p.group(1).lower(), 0.60) if p else 0.60
    return winner, margin


def call_prometheus(prompt):
    from utils import generate_vllm
    from endpoint import model_endpoint_dict
    cfg = model_endpoint_dict["prometheus"]
    out, *_ = generate_vllm(
        model=cfg["model_id"],
        endpoint=cfg["url"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1600,
        temperature=0.2,
        seed=0,
    )
    return out


def call_strong(prompt, base_url, api_key, model, retries=3):
    import urllib.request
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1600,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  strong call failed ({attempt+1}): {e}")
            time.sleep(3)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["prometheus", "strong"], required=True)
    ap.add_argument("--base-url", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--chains", default="/root/GoA/outputs/judge_ablation_40_initial_chains.json")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    chains = json.load(open(args.chains))
    out_rows = []
    fallback = 0

    for item in chains:
        idx = item["idx"]
        question = item["instruction"]
        resp = item["initial_responses"]
        names = item["sampled_nodes"]
        keys = list(resp.keys())
        n = len(keys)
        if n < 2:
            continue
        scores = {k: 0.0 for k in keys}
        ncmp = {k: 0 for k in keys}
        pair_details = []
        for ai in range(n):
            for bi in range(ai + 1, n):
                ka, kb = keys[ai], keys[bi]
                prompt = build_prompt(question, resp[ka], resp[kb])
                if args.judge == "prometheus":
                    out = call_prometheus(prompt)
                else:
                    out = call_strong(prompt, args.base_url, args.api_key, args.model)
                winner, margin = parse_margin(out)
                if winner is None:
                    fallback += 1
                    winner, margin = "tie", 0.5
                if winner == "A":
                    scores[ka] += margin
                    scores[kb] += 1.0 - margin
                elif winner == "B":
                    scores[kb] += margin
                    scores[ka] += 1.0 - margin
                else:
                    scores[ka] += 0.5
                    scores[kb] += 0.5
                ncmp[ka] += 1
                ncmp[kb] += 1
                pair_details.append({
                    "a": str(ka), "b": str(kb),
                    "result": winner, "margin": margin,
                    "tail": out[-60:],
                })
        avg = {k: scores[k] / ncmp[k] for k in keys}
        s = sum(avg.values())
        norm = {k: v / s for k, v in avg.items()} if s > 0 else {k: 1 / n for k in keys}
        top = max(norm, key=norm.get)
        top_answer = item["answers"][top] if top in item["answers"] else ""
        out_rows.append({
            "idx": idx,
            "gold": item["gold"],
            "sampled_nodes": names,
            "answers": item["answers"],
            "normalized_scores": norm,
            "top_node": top,
            "top_answer": top_answer,
            "top_correct": top_answer == item["gold"],
            "pairs": pair_details,
        })

    correct = sum(1 for r in out_rows if r["top_correct"])
    print(f"judge={args.judge} questions={len(out_rows)} top-chain-correct={correct}/{len(out_rows)} = {correct/max(1,len(out_rows))*100:.2f}%  fallback={fallback}")
    out_path = args.out or f"/root/GoA/outputs/judge_ablation_40_{args.judge}.json"
    json.dump({"judge": args.judge, "summary": {"n": len(out_rows), "top_correct": correct,
               "acc": correct / max(1, len(out_rows)), "fallback": fallback}, "rows": out_rows},
              open(out_path, "w"), ensure_ascii=False, indent=1)
    print("SAVED", out_path)


if __name__ == "__main__":
    main()
