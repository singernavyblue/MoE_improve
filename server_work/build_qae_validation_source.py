#!/usr/bin/env python3
"""Create a reproducible disagreement-focused frozen GPQA validation subset."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def load(path: str) -> Any:
    with open(path) as handle:
        return json.load(handle)


def save(path: str, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def has_disagreement(record: dict[str, Any]) -> bool:
    answers = {answer for answer in record.get("initial_answers", {}).values() if answer in {"A", "B", "C", "D"}}
    return len(answers) >= 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261006)
    args = parser.parse_args()

    eligible = [record for record in load(args.source) if has_disagreement(record)]
    if args.n <= 0 or args.n > len(eligible):
        raise ValueError(f"Requested n={args.n}; only {len(eligible)} disagreement records are available")
    selected = random.Random(args.seed).sample(eligible, args.n)
    selected.sort(key=lambda record: int(record["idx"]))
    save(args.out, selected)
    save(args.manifest, {
        "source": args.source,
        "eligibility": "at least two distinct parseable initial answer letters",
        "eligible_n": len(eligible),
        "selected_n": len(selected),
        "seed": args.seed,
        "selected_indices": [record["idx"] for record in selected],
    })
    print(json.dumps({"eligible_n": len(eligible), "selected_n": len(selected), "seed": args.seed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
