#!/usr/bin/env python3
"""Join frozen GPQA questions with the matching frozen GoA pooling run.

The resulting records contain no QAE outputs.  They retain the original GoA
answer and frozen initial chains, so QAE can be evaluated as a post-hoc,
evidence-constrained selector without regenerating any candidate solutions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: str):
    with open(path) as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="outputs/GPQA_test.json")
    parser.add_argument("--frozen-goa", default="outputs/hard_full_198.json")
    parser.add_argument("--out", default="outputs/qae_pooling_full_source_hard_v2.json")
    args = parser.parse_args()

    questions = load(args.questions)
    frozen = {item["idx"]: item for item in load(args.frozen_goa)}
    if set(frozen) != set(range(len(questions))):
        missing = sorted(set(range(len(questions))) - set(frozen))
        extra = sorted(set(frozen) - set(range(len(questions))))
        raise ValueError(f"frozen GoA/question index mismatch: missing={missing[:5]} extra={extra[:5]}")

    records = []
    for idx, item in enumerate(questions):
        run = frozen[idx]
        answer = run.get("A", {}).get("answer")
        usable_answer = answer if answer in {"A", "B", "C", "D"} else None
        records.append({
            "idx": idx,
            "question": item["question"],
            "gold": item["gold_answer"],
            "stored_goa_answer": usable_answer,
            "initial_answers": run.get("initial_answers", {}),
            "initial_responses": run.get("initial_responses", {}),
            "frozen_source": "hard_full_198.A",
            "baseline_parse_error": None if usable_answer else f"unusable_frozen_A_answer:{answer!r}",
        })

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"wrote {len(records)} frozen QAE records to {target}")


if __name__ == "__main__":
    main()
