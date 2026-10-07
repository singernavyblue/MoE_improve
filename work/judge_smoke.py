#!/usr/bin/env python
"""Smoke-test the Prometheus judge service on one GPQA question."""
import json
import os
import re
import sys

os.environ.setdefault("HF_HOME", "/root/autodl-tmp/hf")
os.environ["HF_HUB_OFFLINE"] = "1"

import requests
from transformers import AutoTokenizer

MODEL = "prometheus-eval/prometheus-7b-v2.0"
URL = "http://localhost:8006/v1/completions"

RUBRIC = (
    "Evaluate the reasoning chain of a response to a graduate-level science "
    "multiple-choice question. Give a single integer score from 1 to 5:\n"
    "1: The answer is wrong and the reasoning is irrelevant, empty, or self-contradictory.\n"
    "2: The answer is wrong and the reasoning contains concrete factual, numerical, or logical errors.\n"
    "3: The answer is correct, but the reasoning has substantive flaws (wrong facts, leaps, or errors that cancel out).\n"
    "4: The answer is correct and the reasoning is mostly sound, with only minor issues.\n"
    "5: The answer is correct and every step of the reasoning is valid and well-supported."
)


def main():
    data = json.load(open("/root/GoA/data/test/GPQA_test.json"))
    item = data[0]
    instruction = (
        f"Question: {item['question']}\n"
        f"Provide your step-by-step reasoning first, and then print \"The answer is (x)\", "
        f"where x is the answer choice (one capital letter), at the end of your response."
    )
    reference = f"The correct answer is ({item['gold_answer']})."
    response = (
        "Let's count the carbon atoms. Cinnamaldehyde has 9 carbons; "
        "methylmagnesium bromide adds one carbon; pyridinium chlorochromate "
        "adds no carbon; the sulfur ylide adds one carbon. Total 11. "
        "The answer is (C)."
    )

    prompt_text = (
        "###Task Instruction:\n"
        f"{instruction}\n\n"
        "###Response to Evaluate:\n"
        f"{response}\n\n"
        "###Reference Answer (Score 5):\n"
        f"{reference}\n\n"
        "###Score Rubric:\n"
        f"{RUBRIC}\n\n"
        "###Feedback:\n"
        "(Write a short feedback: which steps hold and which do not.)\n\n"
        "###Score:\n"
        "("
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt_text}],
        tokenize=False,
        add_generation_prompt=True,
    )

    r = requests.post(
        URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "max_tokens": 512,
            "temperature": 0.2,
        },
        timeout=180,
    )
    r.raise_for_status()
    out = r.json()["choices"][0]["text"]
    print("=== JUDGE OUTPUT ===")
    print(out)
    m = re.search(r"###\s*Score\s*[:\-]?\s*([1-5])", out)
    if not m:
        m = re.search(r"\[Result\]\s*([1-5])", out)
    if not m:
        m = re.search(r"overall score is\s*([1-5])", out)
    print("=== PARSED SCORE ===")
    print(m.group(1) if m else "NOT FOUND")


if __name__ == "__main__":
    sys.exit(main())
