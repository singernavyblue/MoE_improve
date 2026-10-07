import json
import re

LOG = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/work/gpqa6-badcases-full.log"
OUT = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa6_badcase_transcripts.md"
OUTJSON = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/work/gpqa6-badcases-output.json"

text = open(LOG).read()
parts = re.split(r"(?=2026-08-02 \d{2}:\d{2}:\d{2}\.\d{3} \|)", text)

records = []
for p in parts:
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| (INFO|DEBUG|WARNING|ERROR)\s*\| (.+?):(\d+) - (.*)$", p, re.S)
    if m:
        records.append((m.group(1), m.group(2), m.group(3), m.group(5).strip("\n")))


def msg_after(record, marker):
    return record[3].split(marker, 1)[1] if marker in record[3] else None


items = []
cur = None
last_model = None

for r in records:
    ts, level, src, msg = r

    if level == "INFO" and "Node Sampling" in msg and "FULL_PROMPT" not in msg:
        cur = {"ts": ts, "node_prompt": None, "node_response": None, "sampled": None,
               "initials": [], "init_conf": None, "edges": [], "edges_info": None,
               "mp": [], "pool": None, "final_answer": None}
        items.append(cur)
        last_model = None
        continue
    if cur is None:
        continue

    if "Sending messages" in msg:
        mm = re.search(r"to `([^`]+)`\.", msg)
        last_model = mm.group(1) if mm else last_model
        continue

    if "FULL_PROMPT" in msg:
        body = msg_after(r, "FULL_PROMPT:")
        if body is None:
            continue
        if "[Node Sampling]" in msg:
            cur["node_prompt"] = body
        elif "Initial Response -" in msg:
            mm = re.search(r"Initial Response - (\w+)", msg)
            cur["initials"].append({"model": mm.group(1) if mm else "?", "prompt": body})
        elif "Edge Sampling -" in msg:
            mm = re.search(r"Edge Sampling - (\w+)", msg)
            cur["edges"].append({"model": mm.group(1) if mm else "?", "prompt": body})
        elif "Graph Pooling" in msg:
            cur["pool"] = {"model": last_model, "prompt": body}
        elif "Round 1/1" in msg:
            stage = "S->T" if "S -> T" in msg else "T->S"
            cur["mp"].append({"stage": stage, "model": last_model, "prompt": body})
        continue

    if "FULL_RESPONSE" in msg:
        body = msg_after(r, "FULL_RESPONSE:")
        if body is None:
            continue
        if "[Node Sampling]" in msg:
            cur["node_response"] = body
        elif "Initial Response -" in msg:
            mm = re.search(r"Initial Response - (\w+)", msg)
            for e in cur["initials"][::-1]:
                if e["model"] == (mm.group(1) if mm else "?") and "response" not in e:
                    e["response"] = body
                    break
        elif "Edge Sampling -" in msg:
            mm = re.search(r"Edge Sampling - (\w+)", msg)
            for e in cur["edges"][::-1]:
                if e["model"] == (mm.group(1) if mm else "?") and "response" not in e:
                    e["response"] = body
                    break
        elif "Graph Pooling" in msg:
            if cur["pool"]:
                cur["pool"]["response"] = body
        elif "Round 1/1" in msg:
            for e in cur["mp"][::-1]:
                if "response" not in e:
                    e["response"] = body
                    break
        continue

    if "Sampled Nodes:" in msg:
        cur["sampled"] = msg.split("Sampled Nodes:")[1].strip()
    elif "Initial Confidences:" in msg:
        cur["init_conf"] = msg.split("Initial Confidences:")[1].strip()
    elif "Generated edges for Source Nodes:" in msg:
        cur["edges_info"] = msg.strip()
    elif "Graph Pooling initiated" in msg:
        pass

output = json.load(open(OUTJSON))
assert len(output) == len(items) == 5, (len(output), len(items))

COMMENTARY = {
    1: {
        "type": "类型一｜图机制淹没正确初始答案（共识偏置）",
        "text": (
            "三个采样模型给出的初始答案：mathstral=B、qwen=D、biomedical=C（唯一正确）。"
            "边采样阶段，三个评分者给正确回答 C 的分数全部最低（mathstral 评 B/C=0.7/0.3，qwen 评 D/C=0.6/0.4，biomedical 评 D/B=0.8/0.2），"
            "正确回答所在的边权重最弱。消息传递阶段，唯一答对的 biomedical 在看到 mathstral 和 qwen 的回答后主动改口成 D（'the answer is still 10 carbon atoms'），"
            "两个 T→S 更新也全部输出 D。最后图池化（Qwen）在三个 D/B 之间做加权平均，输出 D。"
            "整个过程说明：图的边权重与消息传递存在强烈的'从众共识'倾向——多数模型的错误比少数模型的正确更有影响力，"
            "正确回答即使出现也会被评分压低、被持有者自己放弃。"
        ),
    },
    2: {
        "type": "对照样本（本轮答对，批量轮答错）｜采样波动",
        "text": (
            "本题（二维量子谐振子）在批量运行时 6 模型答错（预测 B），本轮重跑答对（A）。"
            "mathstral 与 qwen 初始都给出 A，biomedical 输出格式损坏（置信度 -1），边采样后消息传递与池化都保持 A。"
            "把它列为对照样本，用于说明同一配置的准确率有 ±4~8% 的采样波动，单批高低不能作为结论依据。"
        ),
    },
    3: {
        "type": "类型二｜指令理解缺陷 + 回音室固化（全模型共同误解）",
        "text": (
            "题目问'以下关于 SARS-CoV-2 的表述错误的是（except）'，即选唯一正确的一项（D）。"
            "三个模型（biomedical、mathstral、qwen）的初始回答全部给出 A，而且它们的推理本身都识别出了 D 正确（'Statement D: ... correct'），"
            "却在最后一步把'选出错误项'当成了目标，输出 A。三个模型犯的是同一个指令理解错误。"
            "边采样给彼此的打分都很高（0.7~0.8），消息传递没有引入任何新信息，只是让三个模型互相确认了同一个错误理解，"
            "图池化在'三个 A'之间做平均，错误被完全固化。这类错误是图框架最难救的：当所有模型在同一个点上共同犯错时，"
            "'互相借鉴'只会把错误放大而不是纠正。"
        ),
    },
    4: {
        "type": "对照样本（本轮答对，批量轮答错）｜采样波动",
        "text": (
            "本题（烃类混合物的氢原子计数）在批量运行时答错（预测 C），本轮重跑答对（B）。"
            "mathstral 与 qwen 初始均为 B，biomedical 为 D；边采样与消息传递后两个模型保持在 B，池化输出 B。"
            "同样属于采样波动范围的对照样本。"
        ),
    },
    5: {
        "type": "类型三｜少数正确者被多数错误带偏（从众翻车）",
        "text": (
            "本题（四步立体化学合成）中 mathstral 的初始回答 B 是正确的，qwen 与 biomedical 都答 A。"
            "边采样：qwen 评 A/B=0.8/0.2、biomedical 评 A/B=0.8/0.2，都倾向错误的 A；mathstral 评 B/A=0.7/0.3 倾向自己。"
            "消息传递 S→T 阶段，唯一的正确者 mathstral 在看到两个 A 后把答案改成了 A；T→S 阶段它又改回 B，"
            "但此时图池化（Qwen）拿到的消息已经以 A 为主，最终输出 A。"
            "与类型一相似但机制更直接：正确模型在'参考他人'时动摇，而动摇后的多数意见又进入池化，正确者没能把局面拉回来。"
        ),
    },
}


def fmt(code, lang=""):
    return f"```{lang}\n{code}\n```"


lines = []
lines.append("# GoA 6 模型 GPQA Bad Case 完整交互记录\n")
lines.append("> 5 个代表性错误样本，单进程重跑（num_proc=1），完整记录每次模型调用的提示词与回答。")
lines.append("> 配置：6 模型池（qwen/qwen_coder/mathstral/BioMistral/finance_llama/saul），top_k=3，rounds=1，mean 池化，temperature=0.7\n")

for n, (it, out) in enumerate(zip(items, output), 1):
    q = out["question"][:150].replace("\n", " ")
    lines.append(f"\n---\n\n## 例题 {n}（gold={out['gold_answer']}，最终预测={out['answer']}，采样节点={out['sampled_nodes']}）\n")
    c = COMMENTARY.get(n)
    if c:
        lines.append(f"**{c['type']}**\n")
    lines.append(f"**题目**：{q}...\n")

    # 1. node sampling
    lines.append("### 1. 节点采样（meta=Qwen）\n")
    lines.append("meta 模型收到：题目 + 6 个模型的领域描述卡片，要求选 3 个最合适的模型。")
    lines.append(f"**输出**：`{it['node_response']}`")
    lines.append(f"\n**Sampled Nodes**：`{it['sampled']}`\n")
    lines.append("**节点采样完整提示词**（前 2500 字符）：")
    lines.append(fmt(it["node_prompt"][:2500], "text"))

    # 2. initial responses
    lines.append("\n### 2. 初始回答（每个采样节点独立作答）\n")
    for e in it["initials"]:
        lines.append(f"#### 模型 {e['model']}\n")
        lines.append("**提示词**：")
        lines.append(fmt(e.get("prompt", "")[:1500], "text"))
        lines.append("**完整回答**：")
        lines.append(fmt(e.get("response", ""), "text"))
    if it["init_conf"]:
        lines.append(f"\n**Initial Confidences**：`{it['init_conf']}`\n")

    # 3. edge sampling
    lines.append("\n### 3. 边采样（评估各回答的可信度）\n")
    for e in it["edges"]:
        lines.append(f"#### 模型 {e['model']} 打分\n")
        lines.append("**提示词**（含被评分的两个回答）：")
        lines.append(fmt(e.get("prompt", "")[:1800], "text"))
        lines.append(f"**评分输出**：`{e.get('response', '')}`")
    lines.append(f"\n**生成边**：{it['edges_info']}\n")

    # 4. message passing
    lines.append("\n### 4. 消息传递 Round 1/1\n")
    for e in it["mp"]:
        direction = "S→T（目标模型参考源模型后修正）" if e["stage"] == "S->T" else "T→S（源模型参考目标模型修正后定稿）"
        lines.append(f"#### [{e['stage']}] 调用模型 `{e['model']}` —— {direction}\n")
        lines.append("**提示词**（含其他模型回答）：")
        lines.append(fmt(e.get("prompt", "")[:2000], "text"))
        lines.append("**完整回答**：")
        lines.append(fmt(e.get("response", ""), "text"))

    # 5. graph pooling
    lines.append("\n### 5. 图池化（Graph Pooling - Weighted Mean，meta=Qwen）\n")
    lines.append("meta 模型收到所有节点的最终回答，加权平均后输出最终答案。")
    lines.append("**提示词**：")
    lines.append(fmt(it["pool"].get("prompt", "")[:2000] if it["pool"] else "", "text"))
    lines.append("**最终回答**：")
    lines.append(fmt(it["pool"].get("response", "") if it["pool"] else "", "text"))

    if c:
        lines.append("\n### 为什么错（点评）\n")
        lines.append(c["text"].replace("\n", " ") + "\n")

lines.append("\n---\n\n## 类型总览\n")
lines.append("| 类型 | 例题 | 失败链条 |")
lines.append("|---|---|---|")
lines.append("| 类型一：图机制淹没正确初始答案（共识偏置） | 例题 1 | 正确 C 初始已出现 → 边评分全部最低 → 持有者被说服改答 D → 池化输出 D |")
lines.append("| 类型二：指令理解缺陷 + 回音室固化 | 例题 3 | 三个模型都识别出 D 正确却都输出 A → 消息传递互相确认错误 → 错误固化 |")
lines.append("| 类型三：少数正确者被多数带偏 | 例题 5 | mathstral 初始 B 正确 → 看到两个 A 后改答 A → 池化以 A 为主 → 输出 A |")
lines.append("| 对照：采样波动 | 例题 2、4 | 批量轮答错、重跑答对，同一配置 ±4~8% 波动 |")

open(OUT, "w").write("\n".join(lines))
print(f"transcripts written: {OUT}  items={len(items)}")
