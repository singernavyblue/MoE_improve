# MoE Improve: 多模型推理诊断实验

本仓库用于验证多模型推理诊断与可信融合方法。当前重点不是产品化，而是以可重复、可审计的实验比较不同技术路线：

- 原始 A-pool；
- 全量 Claim 提取；
- span-first 冲突定位；
- 后续的题型分类、差异归因与动态主张路线。

主要实验代码位于 server_work，技术与实验方案位于 docs。

## 研究原则

- 冻结模型回答后再比较技术路线；
- 每次答案修改必须有可回溯的直接证据；
- 同时报告修正数、破坏数和净收益；
- 不将模型投票数视为事实证据。

## 文档

- [实验技术方案](docs/EXPERIMENT_TECHNICAL_PLAN.md)
- [产品方向草案](server_work/PRODUCT_DESIGN.md)
- [span-first 混合模块技术文档](server_work/SPAN_HYBRID_TECHNICAL.md)

## 本地凭证

所有 API Key 必须通过环境变量提供，例如：

~~~bash
export DEEPSEEK_API_KEY="..."
~~~

生成的输出、日志、缓存和任何含有历史明文凭证的旧脚本均不会被纳入版本控制。
