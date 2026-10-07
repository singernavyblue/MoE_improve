# Span-first 混合冲突定位模块：技术设计文档

## 1. 概述

本模块实现面向多模型选择题推理链的 **span-first（证据片段优先）混合流水线**。它不尝试从每条推理链完整抽取原子主张，而是仅在模型答案不一致时，定位可能影响答案的跨模型矛盾，并对该矛盾做盲验证。

实现入口：

- 本地源码：run_qae_localized.py
- 远端隔离部署名：/root/GoA/run_qae_span_hybrid.py
- 一键运行器：run_qae_span_hybrid.sh

它复用既有 QAE 的 hard、verify、ledger、guard、clean/rebuttal、pool 后半段，但替换了前半段的“全量模型生成 Claim ledger”：

~~~mermaid
flowchart LR
  A[冻结的三条推理链] --> B[程序切分 lossless spans]
  B --> C{初始答案是否分歧?}
  C -- 否 --> X[不建立冲突候选]
  C -- 是 --> D[程序检索跨模型 span 对]
  D --> E[D0 题型分类与差异归因]
  E -- 不可验证 --> K[显式保留 A-pool]
  E -- 可验证的一对 span --> F[模型仅判定已列 span 对]
  F --> G{严格结构与证据门}
  G -- 拒绝 --> X
  G -- 通过 --> H[构造 D1 冲突与盲验证问题]
  H --> I[三模型独立盲验证]
  I --> J[证据账本与直接性审查]
  J -- DIRECT --> L[可约束安全 pool]
  J -- 非 DIRECT --> K
~~~

核心原则：**程序拥有来源与候选空间，模型只做受限的语义判断；没有通过门控的内容不能成为证据，也不能改写答案。**

## 2. 设计动机与边界

### 2.1 要解决的问题

传统全量 Claim 抽取有三个工程风险：

1. 模型会把原文没有说过的归纳写进 Claim；
2. Claim 虽附带 quote/span，实体、属性、方向、条件仍可能和 quote 语义错配；
3. 大量与答案分歧无关的 Claim 会制造候选组合、定位器调用和伪冲突。

本模块将“生成所有原子主张”换成“先找可能矛盾的原文片段，后只为已确认矛盾建立结构化 Claim”。

### 2.2 不承担的职责

- 不证明所有推理链中的所有主张均已覆盖；
- 不把检索分数当成冲突概率或证据强度；
- 不以模型投票替代事实验证；
- 不在证据不足时主动更换 A-pool。

因此它优化的是 **高精度、可审计的冲突介入**，而不是主张提取召回率的上界。

## 3. 输入、持久化状态与输出

### 3.1 最小输入记录

每条记录至少需要：

~~~json
{
  "idx": 10,
  "question": "含选项的原题",
  "gold": "D",
  "stored_goa_answer": "D",
  "initial_answers": {"0": "A", "1": "B", "2": "D"},
  "initial_responses": {"0": "冻结推理链", "1": "冻结推理链", "2": "冻结推理链"}
}
~~~

gold 只用于离线评估，任何提示词和决策阶段均不读取它。

### 3.2 模块新增状态

| 字段 | 产生阶段 | 作用 |
|---|---|---|
| swarm_spans | spans | 程序生成的、带原始字符 offset 的完整 span 账本 |
| swarm_span_candidates | span_candidates | 只含跨模型 span ID 对的可审计检索结果 |
| swarm_diagnosis | diagnose | D0 的题型、差异归因、可验证性和唯一允许进入定位的 span 对 |
| swarm_conflict | localize | 拒绝原因或通过严格验证的唯一 D1 冲突；通过时保存 core pair、上下文包与字段级 offset |
| qae_plan | localize | 只有已通过冲突门时才写入 D1-E1 盲验证任务 |
| qae_ledger | verify / ledger | 多模型盲验证答案及其归一化证据等级 |
| swarm_guard | guard | 证据是否能直接裁决 D1 的最终授权结果 |

下游沿用 qae_clean、qae_rebuttal、qae_pooler 和 qae_final_answer。

### 3.3 已接受冲突的输出契约

一个被正式接受的 swarm_conflict 必须含两条结构化 Claim；每条均可回到冻结文本：

~~~json
{
  "status": "CONFLICT",
  "conflict_id": "D1",
  "span_refs": ["M1-S2", "M2-S4"],
  "verification_route": "fact",
  "structured_claims": [
    {
      "span_ref": "M1-S2",
      "model": "M1",
      "start": 39,
      "end": 189,
      "entity": "subgenomic rna transcription",
      "attribute": "process continuity",
      "conditions": "none",
      "direction": "other",
      "entity_span": "Subgenomic RNA transcription ...",
      "attribute_span": "discontinuous process"
    }
  ]
}
~~~

start:end、quote、entity_span、attribute_span 和可选的 condition_span 共同构成审计链。

对于需要把“实体定义”和“计算结果”组合起来审计的 D1，记录还会保存
`context_span_refs` 与每个字段的 `support`。每个 support 同时含其
`span_ref`、父 span 的 `source_start/source_end` 和精确子串的
`anchor_start/anchor_end`；因此上下文不会被拼成一段失去来源的文本。

## 4. 处理阶段

### 4.1 hard

复用既有的确定性数值/符号规则。若已有唯一、程序拥有的 HARD 约束，记录标为 SKIPPED_HARD，不进入冲突定位。

### 4.2 spans：无损原文账本

函数 _source_spans 对每个 initial_responses[Mk] 做确定性切分：

- 换行与句末 . ! ? 是边界；
- 仅裁去 span 两端空白，start/end 永远相对于原始冻结字符串；
- 没有边界的文本仍保留为一个 span；
- 保存 span_id（如 M2-S4）、模型编号、offset、完整文本、内容 token、是否含直接选项回答等元数据。

这一步不调用模型。is_direct_answer=true 的 span 仍保留供审计，但不会作为冲突检索候选，避免“选项字母不同”本身变成伪证据。

### 4.3 span_candidates：高召回、非语义检索

只在至少两个可解析 initial_answers 字母不同的记录上运行。

候选必须来自两个不同源模型。程序计算：

~~~text
score = 共享词 lexical score + 稀有共享 token 的加权 + 数字/公式/希腊符号 bonus
~~~

检索器按模型对均衡取样，默认每题最多 24 对。若一个模型对没有任何词面/符号重叠，会保留极少量 fallback_information_dense_cross_model_pair；该 fallback 仅防止漏召回，绝不等价于冲突。

### 4.4 diagnose：题型分类与差异归因门

`diagnose` 只看原题和最多 12 个程序检索出的 span 对，不看选项字母、A-pool 或 gold。它输出：

- `problem_type`：数值计算、公式推导、因果机制、条件逻辑、实体关系或开放题；
- `diagnosis_type`：概念/事实、条件范围、实体混淆、公式/计算、证据不足或无可验证冲突；
- `claim_category`：四个初始类别或 `new`；新类别会保留 `new_claim_label`，进入后续归并队列；
- `verification_eligible` 与一对精确 `span_refs`。

程序只接受来自已展示、跨模型 candidate pair 的两条 ref。开放题、证据不足、未授权或格式无效的诊断一律写成 `RETAIN_A_POOL`；这不是“所有推理均无冲突”的负面结论，而是禁止以不足证据干预答案。启用 `--diagnosis-gate` 后，D0 未为 `ELIGIBLE` 的记录不会调用定位器、验证器或 pooler 的干预分支。

### 4.5 localize：受限冲突判断与 Claim 物化

定位模型只看到：

- 原题；
- 已检索的 span 对；
- 每对的 span ID、来源模型、文本片段与检索来源。

它不能引用未列出的 span，也不应输出选项字母。返回 CONFLICT 时，程序要求同时满足：

1. 两个 ref 都在已检索 pair 内；
2. 两个 ref 分属不同源模型；
3. same_entity=true 且 same_conditions=true；
4. entity、attribute 不得为空或 unknown；
5. 两边均有实体与属性的精确连续锚点，且字段可由各自锚点支持；
6. 条件不是 none 时，两边都必须有条件锚点；
7. 冲突类型、验证路线、盲验证问题均为受控合法值；
8. 两侧方向必须由程序判定为**不相容**。

通过后才写入 D1 和 D1-E1；否则仅记录 NO_VALID_SPAN_CONFLICT 及原始响应以供审计。

#### 相邻上下文 / 多 span Claim

核心候选仍严格是 D0 选中的两条跨模型 span；系统没有把检索候选扩展为
任意推理链。定位前，程序会为 core pair 的左右两侧分别构造一个**同一来源模型**
的固定相邻包：默认核心 span 加前后各一条（`--span-context-radius=1`，最大为 2）。

- `span_refs` 始终保留两个 core ID；
- entity、attribute、condition、result 各自都必须输出 `*_ref + *_span`；
- 左字段只能引用左包、右字段只能引用右包，引用包外、另一模型或非连续文本会被程序拒绝；
- 数值冲突在各自 `result_span` 的终值上判断，实体/属性仍须由独立的精确锚点支持；
- 传给 directness guard 的 `claim_refs` 是两个完整审计包，而不是脱离定义的单句结果。

这个设计提高了“相邻定义 + 计算结果”型 Claim 的召回，但没有放宽 exact-span、跨模型、同条件或方向/终值不相容门。

#### 一次受限修复

当候选已是跨模型、已检索、同实体同条件且方向确实相反，但模型遗漏属性/条件锚点时，系统可发起**一次**字段修复调用。修复调用只能补 entity、attribute、conditions 的精确锚点和 route，不能改变 span 对、冲突结论、来源模型或方向。这避免第二次调用重新发明更方便的冲突。

### 4.6 字段、公式和方向门

_field_matches_span 支持三种证据匹配：

1. 普通内容词交集；
2. 符号/公式 fingerprint；
3. HBr 与 hydrogen bromide 的受控化学式别名。

方向先归一为 increase、decrease、unchanged、present、absent、other。仅允许以下类别通过：

- increase ↔ decrease；
- present ↔ absent；
- unchanged ↔ increase/decrease；
- 小型受控定性反向词表，例如 continuous ↔ discontinuous、active ↔ inactive。

数值/计算路线还有一个窄例外：在同一实体、属性、条件且两侧属性锚点均已精确落回原文时，形如 `7.5 + 0.3 = 7.8` 与 `10^0.3 ≈ 2.0` 的**终值 decimal 不相等**可作为冲突依据。它不尝试判断一般公式等价性、科学计数法或未给出结果的表达式；这些仍须走符号/数值验证，不能由词面差异放行。

因此两个都为 increase 的表述，即使局部措辞不同，也不会触发定位器或验证调用。

验证路线也使用受控映射：

| 模型输出 | 归一化 route |
|---|---|
| calculation | numeric |
| formula | symbolic |
| definition / comparison | fact |

### 4.7 verify：盲验证

对每个 D1-E1，Qwen、Mathstral、BioMistral 独立回答同一事实/数值问题。提示中不含选项字母、A-pool、任一原始推理链或其他验证器的答案。

run_span_verify 使用 vLLM 的 /v1/chat/completions，并用 _VLLM_SERVED_MODELS 映射本地 server 的 served model name。无效 JSON 或 HTTP 失败写成 UNKNOWN，不能生成正面证据。

### 4.8 ledger、guard 和安全池化

ledger 仅在至少两路具体答案语义一致时给 STRONG。随后 guard 检查该结论是否**直接**区分 D1 的两侧主张：

- DIRECT + ADMIT：保留该证据对选项的支持/反驳；
- INDIRECT、UNRELATED 或 REJECT：清空 supports/contradicts，最终安全回退到 A-pool。

这使“相关事实”无法越级成为“可改变选择题答案的事实”。

## 5. 与旧 Claim-normalization 路径的关系

该文件仍保留旧的 claims → normalize → localize 实验路径，以便消融比较。--span-hybrid 启用本文档描述的路径。

需要特别注意：

- --no-coreference-gate、--no-field-span-gate、--no-hbr-dedup 是旧 Claim-normalization 路径的消融开关；
- span-first 路径使用自己的精确锚点、跨模型 pair、条件与方向门；
- span-first 路径已经在 `valid` 与一次字段修复的资格检查中接入 `_subject_is_resolved`；`they`、`a`、`it` 等不能唯一指向实体的字段会被拒绝。

## 6. 运行方式

### 6.1 完整远端运行

~~~bash
cd /root/GoA
LIMIT=10 \
SOURCE=outputs/qae_span_hybrid_focus10_source_20261007.json \
PREFIX=outputs/qae_span_hybrid_focus10_v3_20261007 \
bash run_qae_span_hybrid.sh
~~~

运行器依次执行：

~~~text
hard → spans → span_candidates
→ diagnose(Qwen, D0)
→ localize(Qwen, 仅 D0 授权的 pair)
→ verify_needed → verify(Qwen, Mathstral, BioMistral；仅存在 D1-E1 时)
→ ledger → guard → clean → rebuttal → pool → summary
~~~

它在单 GPU 上顺序装载模型，HF_HUB_OFFLINE=1 以避免评测时下载模型。`verify_needed` 会在没有 D1 盲验证任务时跳过三次验证模型加载；诊断门启用时，clean、rebuttal、pool 对无 HARD/STRONG ledger 的记录也会程序化保留 A-pool，不再生成必然被丢弃的随机复解。

### 6.2 单阶段恢复

每阶段写回同一个 OUT JSON；已有状态会被跳过。因此中断后可使用相同 SOURCE/PREFIX 重跑。不要让两个进程同时写同一个 OUT 文件。

~~~bash
python run_qae_span_hybrid.py \
  --stage localize --model qwen --span-hybrid \
  --source outputs/input.json --out outputs/run.json \
  --summary outputs/run_summary.json --limit 0 \
  --span-candidate-limit 24
~~~

### 6.3 静态检查

~~~bash
PYTHONPYCACHEPREFIX=/tmp/qae_pycache python -m py_compile run_qae_span_hybrid.py
bash -n run_qae_span_hybrid.sh
~~~

## 7. 可观测性和验收指标

summary 的 span_hybrid 段包含：

| 指标 | 含义 |
|---|---|
| raw_span_count | 完整原文账本中的 span 数 |
| records_with_complete_span_ledger | 成功建立完整账本的记录数 |
| retrieved_cross_model_pair_count | 程序检索出的跨模型 pair 数 |
| localized_conflict_count | 通过定位结构门的冲突数 |
| materialized_structured_claim_count | 仅为已接受冲突建立的 Claim 数 |

同时应联合查看：

- diagnosis 的 `ELIGIBLE / RETAIN_A_POOL` 比例、题型和归因分布、`new_claim_labels`；
- conflict_localization.conflict_status：拒绝与接受比例；
- directness_guard：有多少强验证证据被授权进入池化；
- changed_with_admitted_direct_evidence：所有答案变更是否都有直接证据；
- paired_final_vs_A_pool.fixed/broken：相对 A-pool 的净改善与回归。

## 8. 已完成的 10 题验证（2026-10-07）

样本是 10 个初始模型答案确有分歧的 GPQA 记录（idx = 2、7、8、9、10、12、13、14、16、17），不是随机全量估计。

| 项目 | 结果 |
|---|---:|
| 原始 span | 212 |
| 跨模型候选对 | 192 |
| 通过定位门的冲突 | 1 |
| 物化 Claim | 2 |
| STRONG 盲验证证据 | 1 |
| 获 directness guard 授权的证据 | 0 |
| A-pool 准确率 | 6/10 |
| 最终准确率 | 6/10 |
| 修正 / 破坏 | 0 / 0 |

唯一确认的真实冲突是“subgenomic RNA transcription 是 continuous 还是 discontinuous”。Qwen 与 Mathstral 一致回答 discontinuous；BioMistral 返回不完整 JSON，按规则记为 UNKNOWN。directness guard 将该证据判为 INDIRECT，不允许它直接重写选择题答案。该保守行为避免了 pooler 将答案错误改为 C。

对应产物：

- qae_span_hybrid_focus10_v3_20261007.json
- qae_span_hybrid_focus10_v3_20261007_summary.json

## 9. 已知限制与后续工作

1. **BioMistral 的不完整 JSON 只会降级为 UNKNOWN。** 可通过 JSON schema、constrained decoding 或更稳健的尾部闭合修复改善可用率。
2. **模型切换要验证模型身份。** 运行器当前以 /v1/models 的端口可用性作为就绪信号；更稳妥的实现应确认返回 ID 等于将使用的 served model，避免切换瞬间误连旧 server。
3. **验证事实未必能映射到唯一选项。** 不应靠放宽 guard 解决；应增强“证据只排除特定选项”的部分约束映射，并继续禁止由单条事实直接猜最终选项。
4. **诊断精度与冲突召回率没有人工 gold set。** 当前 10 题仅证明旧门控精度与安全回退；新 D0 需要在 20--50 道人工审计题上报告题型/归因一致性、错误放行和漏放行。
5. **动态类别尚未自动合并。** `new_claim_label` 先进入审计队列；合并为稳定类别需要人工或独立的离线归并实验。
