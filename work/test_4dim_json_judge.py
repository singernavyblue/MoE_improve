"""Smoke: does prometheus emit parseable {D1..D4} JSON for the new judge?"""
import json
import sys

sys.path.insert(0, "/root/GoA")
from endpoint import model_endpoint_dict
from utils import generate_vllm
from modules import _parse_4dim_scores

chains = json.load(open("/root/GoA/outputs/judge_ablation_40_initial_chains.json"))
item = chains[0]
resp = list(item["initial_responses"].values())[0]

rubric = (
    "Score this reasoning chain on four independent dimensions, each 1 (worst) "
    "to 5 (best):\n"
    "D1 Goal Alignment (gate): 5=correctly identifies the question type and respects "
    "every qualifier; 4=understands the question but misses one minor qualifier; "
    "3=understands the type but substitutes the goal midway; 2=answers a related but "
    "different question; 1=inverts the question type (e.g. an 'except' question answered "
    "with the wrong item).\n"
    "D2 Information Utilization: 5=every fact correct, all given numbers/conditions used, "
    "options checked one by one; 4=mostly correct, one non-critical condition missed; "
    "3=conclusion correct but a substantive factual error (errors cancel out); "
    "2=wrong key fact/reagent/property drives the wrong conclusion; 1=ignores the given "
    "information or fabricates facts.\n"
    "D3 Result Verification: 5=explicit consistency check (conclusion vs reasoning, vs "
    "options, vs numbers); 4=consistent but no explicit check; 3=second-guesses but does "
    "not fully verify; 2=conclusion directly contradicts the chain's own reasoning and "
    "the model does not notice; 1=no verification, assertion without support, or an "
    "obviously impossible result.\n"
    "D4 Efficiency: 5=direct, complete, no filler; 4=minor redundancy; 3=one or two "
    "repeated arguments; 2=many detours, padding length to fake rigor; 1=pure restatement "
    "or corrupted output.\n"
    "Rules: score each dimension independently; length and confidence are NOT correctness; "
    "if D1 <= 2 the chain is failed overall regardless of D2-D4."
)

prompt = (
    "###Task Instruction:\n"
    f"{item['instruction']}\n\n"
    "###Response to Evaluate:\n"
    f"{resp}\n\n"
    "###Reference Answer (Score 5):\n"
    "No reference answer is provided. Evaluate the response on its own merits.\n\n"
    "###Score Rubric:\n"
    f"{rubric}\n\n"
    "###Feedback:\n"
    "(Write 2-3 sentences: which steps hold, which fail, and whether the "
    "conclusion is supported by the reasoning.)\n\n"
    "###Score JSON:\n"
    '{"D1": <1-5>, "D2": <1-5>, "D3": <1-5>, "D4": <1-5>}'
)

cfg = model_endpoint_dict["prometheus"]
out, *_ = generate_vllm(
    model=cfg["model_id"],
    endpoint=cfg["url"],
    messages=[{"role": "user", "content": prompt}],
    max_tokens=800,
    temperature=0.2,
    seed=0,
)
print("===RAW OUTPUT===")
print(out)
print("===PARSED===")
print(_parse_4dim_scores(out))
