import json
import os

results_dir = "/root/autodl-tmp/gpqa_results6"
merged = []
for i in range(1, 5):
    path = os.path.join(results_dir, f"batch{i}.json")
    if not os.path.exists(path):
        print(f"MISSING: {path}")
        continue
    with open(path) as f:
        batch = json.load(f)
    ok = sum(1 for item in batch if str(item.get("answer")) == str(item.get("gold_answer")))
    print(f"batch{i}: {len(batch)} items, accuracy={ok}/{len(batch)} = {ok / len(batch) * 100:.2f}%")
    merged.extend(batch)

if not merged:
    print("No results to merge.")
    raise SystemExit(1)

correct = sum(1 for item in merged if str(item.get("answer")) == str(item.get("gold_answer")))
print(f"TOTAL: {len(merged)} items, correct={correct}, accuracy={correct / len(merged) * 100:.2f}%")

out = os.path.join(results_dir, "GPQA_test_merged.json")
with open(out, "w") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
print(f"saved: {out}")
