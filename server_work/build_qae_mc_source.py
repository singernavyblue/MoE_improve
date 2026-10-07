#!/usr/bin/env python3
"""Build a frozen QAE source from an existing paired MCQ run.

The paired run supplies frozen initial chains and its A answer; the dataset
file supplies the question/options and gold.  No model is called here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: str):
    with open(path) as handle:
        return json.load(handle)


def question_with_options(item: dict) -> str:
    question = str(item.get("question", ""))
    choices = item.get("choices", item.get("options"))
    if isinstance(choices, list) and choices and "(A)" not in question:
        letters = "ABCDEFGHIJ"
        question += "\n\nThe options are: " + " ".join(
            f"({letters[i]}) {value}" for i, value in enumerate(choices)
        )
    return question


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--paired", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    raw = load(args.data)
    paired = load(args.paired)
    by_idx = {int(item["idx"]): item for item in paired}
    records = []
    for idx, item in enumerate(raw):
        if idx not in by_idx:
            continue
        frozen = by_idx[idx]
        baseline = frozen.get("A_answer")
        if baseline not in set("ABCDEFGHIJ"):
            baseline = None
        records.append({
            "idx": idx,
            "dataset": args.dataset,
            "question": question_with_options(item),
            "gold": str(item.get("gold_answer", frozen.get("gold", ""))),
            "stored_goa_answer": baseline,
            "initial_answers": frozen.get("initial_answers", {}),
            "initial_responses": frozen.get("initial_responses", {}),
            "frozen_source": str(Path(args.paired)),
        })
    if not records:
        raise ValueError("no paired records matched the dataset")
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"wrote {len(records)} records to {target}")


if __name__ == "__main__":
    main()
