# -*- coding: utf-8 -*-
"""Server-side smoke test: does the 4-dim rubric actually produce D1-D4 scores?"""
import sys
sys.path.insert(0, "/root/GoA")
from endpoint import model_endpoint_dict
from utils import generate_vllm

rubric_4dim = (
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

question = (
    "Question: trans-cinnamaldehyde was treated with methylmagnesium bromide, forming "
    "product 1. 1 was treated with pyridinium chlorochromate, forming product 2. "
    "3 was treated with (dimethyl(oxo)-l6-sulfaneylidene)methane in DMSO at elevated "
    "temperature, forming product 3. how many carbon atoms are there in product 3? "
    "The options are: (A) 12 (B) 14 (C) 11 (D) 10"
)
resp_a = (
    '{"reasoning": "The reactions described involve the addition of methyl groups, the '
    'oxidation of an alcohol to a carbonyl, and a cyclization reaction. These reactions '
    'do not change the number of carbon atoms in the molecule. Therefore, the number of '
    'carbon atoms in product 3 is the same as in product 1.", "answer": "B", '
    '"confidence_level": 1.0}'
)
resp_b = (
    '{"reasoning": "Cinnamaldehyde has 10 carbon atoms. In 1, methyl is removed, and one '
    'carbon atom is added. In 2, one carbon atom is removed. In 3, no carbon atom is '
    'removed, and one carbon atom is added. Therefore, product 3 has 11 carbon atoms.", '
    '"answer": "C", "confidence_level": 1.0}'
)

reference_line = "No reference answer is provided. Evaluate the two responses on their own merits."
prompt_content = (
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
    f"{reference_line}\n\n"
    "###Score Rubric:\n"
    f"{rubric_4dim}\n\n"
    "###Feedback:\n"
)

cfg = model_endpoint_dict["prometheus"]
out, *_ = generate_vllm(
    model=cfg["model_id"],
    endpoint=cfg["url"],
    messages=[{"role": "user", "content": prompt_content}],
    max_tokens=1600,
    temperature=0.2,
    seed=0,
)
print("===JUDGE OUTPUT===")
print(out)
