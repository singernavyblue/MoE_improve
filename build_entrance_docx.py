# -*- coding: utf-8 -*-
"""生成《入学测试设计报告——能力画像方案》Word 文档。"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from build_report_docx import (
    style_font,
    run_font,
    add_numbering_defs,
    add_list_para,
    make_table,
    add_heading,
    add_body,
    add_rich,
    add_bottom_rule,
    add_callout,
    add_page_number,
)

INK_BLUE = RGBColor(0x0B, 0x25, 0x45)
MUTED = RGBColor(0x59, 0x59, 0x59)


def add_ref(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.1
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.first_line_indent = Inches(-0.3)
    r = p.add_run(text)
    run_font(r, size=10)


def add_code(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.05
    p.paragraph_format.left_indent = Inches(0.25)
    r = p.add_run(text)
    run_font(r, size=9)
    r.font.name = "Courier New"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "PingFang SC")


def build():
    doc = Document()
    doc.core_properties.title = "入学测试设计报告"

    normal = doc.styles["Normal"]
    style_font(normal, size=11)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.1
    for name, size, color, before, after in (
        ("Heading 1", 16, RGBColor(0x2E, 0x74, 0xB5), 16, 8),
        ("Heading 2", 13, RGBColor(0x2E, 0x74, 0xB5), 12, 6),
        ("Heading 3", 12, RGBColor(0x1F, 0x4D, 0x78), 8, 4),
    ):
        st = doc.styles[name]
        style_font(st, size=size, bold=True, color=color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.line_spacing = 1.1

    add_numbering_defs(doc)

    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    fp = section.footer.paragraphs[0]
    fp.paragraph_format.space_before = Pt(0)
    fp.paragraph_format.space_after = Pt(0)
    add_page_number(fp)

    # ---------- 首屏 ----------
    first_p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    first_p.paragraph_format.space_before = Pt(0)
    first_p.paragraph_format.space_after = Pt(2)
    r = first_p.add_run("入学测试设计报告——能力画像方案")
    run_font(r, size=22, bold=True, color=INK_BLUE)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(10)
    rs = sub.add_run("摸底题集 · 能力维度 · 建档方式 · 与裁判衔接（论文依据版）")
    run_font(rs, size=13, color=MUTED)

    for label, value in (
        ("汇报人", "王行杭"),
        ("日期", "2026-08-28"),
        ("任务", "P0 · 入学测试设计"),
        ("状态", "方案完成（待实验）"),
    ):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.1
        rl = p.add_run(label + "：")
        run_font(rl, size=11, bold=True, color=INK_BLUE)
        rv = p.add_run(value)
        run_font(rv, size=11)
    add_bottom_rule(doc, after=12)

    # ---------- 结论速览 ----------
    add_callout(
        doc,
        "结论速览",
        "入学测试 = 给 6 个底层模型做一次分维度摸底考试：按能力维度标注的题（Q 矩阵）→ 统计每模型每维对错 → "
        "用 IRT / CDM 估计能力画像（θ 与掌握概率 α）→ 存成能力画像卡。裁判打分时把画像作为先验，与单题 "
        "pairwise margin 贝叶斯加权，并随每轮评测滚动更新。理论依据：IRT（Rasch/Lord）、认知诊断 CDM（de la Torre）、"
        "属性层次模型（Leighton 等）、证据中心设计（Mislevy）、ADeLe（Nature 2026）、ATLAS 自适应测试。",
    )
    add_body(doc, "", after=2)

    # ---------- 一、方案总览 ----------
    add_heading(doc, "一、方案总览", 1)
    add_body(doc, "整个方案是一条流水线，五个组件环环相扣：")
    add_list_para(doc, "摸底题集：按维度标注的题（150 题，4 维约每维 37 题），与评测题物理隔离。", 110)
    add_list_para(doc, "Q 矩阵：题 × 能力维度的关联矩阵（每题 1 主维 + 0–2 次维）。", 110)
    add_list_para(doc, "作答矩阵：6 模型 × 150 题的对错矩阵。", 110)
    add_list_para(doc, "IRT/CDM 拟合：每维估计 θ（能力）与 α（掌握概率），含置信区间。", 110)
    add_list_para(doc, "能力画像卡：每模型一张 JSON，作为裁判的贝叶斯先验，随评测滚动更新。", 110)
    add_body(doc, "对应导师设计：① 批量摸底画能力地图 = 组件 1–4；② 双重评估（先验 + 单题表现）= 组件 5 接入裁判。", italic=True)

    # ---------- 二、能力维度与 Q 矩阵 ----------
    add_heading(doc, "二、能力维度与 Q 矩阵", 1)
    add_body(doc, "针对 GPQA 知识域与我们已经发现的失败模式，设计 4 个能力维度（D5 指令理解并入 D4，构成“推理与指令”联合维）：")
    make_table(
        doc,
        [1.6, 1.6, 1.4, 1.2, 1.0],
        ["维度", "测什么", "典型题型", "论文依据", "对应失败模式"],
        [
            ("D1 化学机理与分子推理", "反应机理、结构、立体化学", "碳数计算、产物结构、构型判断", "ADeLe 需求维度；CDM", "bad1 肉桂醛碳数"),
            ("D2 物理计算与定量推理", "数值、量纲、方程", "常数计算、单位换算", "IRT 单维能力", "5.1 计算类转错"),
            ("D3 生物分子与机制", "分子生物学、遗传、生化通路", "机制与通路判断", "ADeLe", "bad2 SARS"),
            ("D4 推理与指令（联合维）", "多步推理过程 ＋ 回答契约理解（原 D4 多步演绎 + 原 D5 指令理解合并）", "多步推导、逐条排除、except 反问题", "属性层次模型；ECD 任务模型；Facione 解释", "bad2 分析对输出反、idx61 长链带偏"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_rich(
        doc,
        [
            ("合并理由：", {"bold": True}),
            ("main 非 Diamond 部分中“回答契约”型题极少（仅 5 道），单独做 D5 无法满足 IRT 每维 ≥30 题的要求；"
             "并入 D4 后统计稳定，代价是失去“指令单独诊断”的粒度——通过在 Q 矩阵备注列记录 M（多步）/ I（指令）/ MI（两者）子类型来弥补，"
             "拟合用 4 维，事后分析仍可细分。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Q 矩阵构造（论文背书）：", {"bold": True}),
            ("初版用人工给 150 题标定（每题 1 主维 + 0–2 次维）；扩展版用题目文本嵌入聚类 + LLM 打标自动生成其余题的 Q 行，"
             "即 Scalable Text-Embedding CDM for LLMs（arXiv 2603.14676）的做法——用文本嵌入构造 Q 矩阵先验，减少人工标注；"
             "最后随机抽 20 题人工复核一致性。", {}),
        ],
    )

    # ---------- 三、摸底题集 ----------
    add_heading(doc, "三、摸底题集设计", 1)
    add_body(doc, "题集来源按优先级排列：")
    make_table(
        doc,
        [1.6, 1.0, 1.3, 1.6, 1.0],
        ["来源", "数量", "优点", "风险", "结论"],
        [
            ("GPQA-main 非 test 部分", "每维 30–40，共约 150", "同域、难度真实、零合成噪声", "需确认仓库是否有该划分", "首选"),
            ("GPQA test 198 题复用", "—", "—", "与评测集泄漏，结果作废", "禁用"),
            ("LLM 按维度模板合成", "150", "维度完全可控", "随机性强、可能有错（导师已提示）", "备选，需人工校验＋参考答案锚"),
            ("其它 benchmark 子集（MMLU 专业/MedQA 等）", "150", "现成、有标签", "领域偏移", "补充题源"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_rich(doc, [("防泄漏三原则：", {"bold": True}), ("① 摸底题与评测题物理隔离（不同题、不同来源）；② ADeLe 强调用“需求维度”而非具体题，画像天然抗记忆泄漏；③ 难度覆盖——用 IRT 题目难度 b 分层抽样（易/中/难各约 1/3），避免画像只反映单一难度。", {})])

    # ---------- 四、建档方式 ----------
    add_heading(doc, "四、建档方式", 1)
    add_body(doc, "建档分三层，逐层加信息：")
    make_table(
        doc,
        [1.2, 2.0, 1.7, 1.6],
        ["层", "内容", "方法", "论文依据"],
        [
            ("单维能力 θ", "每模型每维 θ + 标准误 SE", "IRT 2PL 拟合该维作答矩阵", "Rasch 1960；Lord 1980；ATLAS（arXiv 2511.04689）"),
            ("多维掌握 α", "每维掌握/未掌握概率", "CDM / DINA 模型", "de la Torre 2009"),
            ("不确定性", "θ 的置信区间", "后验分布估计", "Laplace-PSN-IRT（arXiv 2607.25257）"),
            ("知识关联", "维度先决 DAG + 低维预测高维", "属性层次模型", "Leighton, Gierl & Hunka 2004"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_body(doc, "能力画像卡（每模型一张 JSON，示例）：", bold=True)
    add_code(
        doc,
        '{\n'
        '  "model": "biomedical_llama",\n'
        '  "theta":  {"D1": 0.4, "D2": -0.2, "D3": 0.9, "D4": 0.1},\n'
        '  "mastery":{"D1": 0.62, "D2": 0.42, "D3": 0.82, "D4": 0.55},\n'
        '  "se":     {"D1": 0.31, "D2": 0.29, "D3": 0.27, "D4": 0.30},\n'
        '  "n_items":{"D1": 37,   "D2": 37,   "D3": 37,   "D4": 39},\n'
        '  "updated_at": "2026-08-28"\n'
        '}'
    )

    # ---------- 五、与裁判衔接 ----------
    add_heading(doc, "五、与裁判的衔接（双重评估）", 1)
    add_rich(
        doc,
        [
            ("贝叶斯框架（Mislevy 2003 ECD）：", {"bold": True}),
            ("后验 ∝ 单题似然 × 能力先验。落地为：", {}),
        ],
    )
    add_code(
        doc,
        "边权重(m) = normalize( w1 × sigmoid(θ_m,D)  +  w2 × pairwise_margin(m) )\n"
        "其中 sigmoid(θ) 或 mastery α 来自能力画像卡；w1 + w2 = 1。"
    )
    add_list_para(doc, "权重校准：在已有的 40 题选链集上网格搜索 w1/w2（先验占比建议 0.2–0.5），用选链正确率选最优。", 110)
    add_list_para(doc, "滚动更新：每跑完一题，把该题对错作为新证据做贝叶斯一步更新（或滑动窗口），画像卡随之刷新——“入学测试”升级为“随考随更新”。", 110)
    add_rich(
        doc,
        [
            ("用法示例：", {"bold": True}),
            ("bad2（except 题，属 D4 联合维中的指令子类）中，若某模型 D4 的 mastery 只有 0.30（多步推理正常、指令理解弱），"
             "避免它把“选正确表述”的错误理解带进共识——这正是导师说的“用已知知识掌握度预测未知解题能力”。", {}),
        ],
    )

    # ---------- 六、落地步骤 ----------
    add_heading(doc, "六、落地步骤与工作量", 1)
    make_table(
        doc,
        [0.8, 2.4, 3.3],
        ["步骤", "内容", "工作量"],
        [
            ("1", "造 Q 矩阵：4 维 × 150 题标定 ＋ 嵌入自动扩展 ＋ 复核", "1–2 天"),
            ("2", "摸底运行：6 模型 × 150 题推理（vLLM，可并行）", "约 2–3 小时"),
            ("3", "IRT 拟合：每维一个 2PL 模型", "脚本运行数分钟"),
            ("4", "生成 6 张能力画像卡（JSON）", "0.5 天"),
            ("5", "40 题集上校准 w1/w2", "1 次短跑"),
            ("6", "全量 198 题跑“画像先验 ＋ pairwise margin”对照基线", "与现有实验同量级"),
        ],
    )
    add_body(doc, "", after=4)

    # ---------- 七、风险 ----------
    add_heading(doc, "七、风险与对策", 1)
    add_list_para(doc, "只有 6 个模型，画像噪声大 → 维度压到 3–5 个；θ 加正则先验；必要时用强模型扩充摸底样本。", 110)
    add_list_para(doc, "D5 并入 D4 后失去指令单独诊断粒度 → Q 矩阵备注列保留 M/I/MI 子类型，IRT 用 4 维联合估计，事后按子类型细分分析。", 110)
    add_list_para(doc, "摸底题与评测题泄漏 → 物理隔离 ＋ ADeLe 需求维度做法。", 110)
    add_list_para(doc, "IRT 拟合不稳定（每维题量不足）→ 每维至少 30 题；样本不足时合并相近维度。", 110)
    add_list_para(doc, "先验与单题信号冲突 → 贝叶斯框架下先验只做收缩（shrinkage），不覆盖强单题证据。", 110)

    # ---------- 八、参考文献 ----------
    add_heading(doc, "八、参考文献", 1)
    refs = [
        "Rein, D., et al. (2023). GPQA: A Graduate-Level Google-Proof Q&A Benchmark. arXiv:2311.09722.",
        "Rasch, G. (1960). Probabilistic Models for Some Intelligence and Attainment Tests. Danish Institute for Educational Research.",
        "Lord, F. M. (1980). Applications of Item Response Theory to Practical Testing Problems. Lawrence Erlbaum.",
        "de la Torre, J. (2009). DINA model and parameter estimation. Journal of Educational and Behavioral Statistics, 34(1), 115–130.",
        "Leighton, J. P., Gierl, M. J., & Hunka, S. M. (2004). The attribute hierarchy method for cognitive assessment. Journal of Educational Measurement, 41(3), 205–237.",
        "Mislevy, R. J., Steinberg, L. S., & Almond, R. G. (2003). On the structure of educational assessments. Measurement, 1(1), 3–62.",
        "Zhou, L., Pacchiardi, L., Martínez-Plumed, F., Sun, L., Stillwell, D., et al. (2026). General scales unlock AI evaluation with explanatory and predictive power. Nature, 652, 58–67.",
        "Li, X., Tang, Y., et al. (2025). Adaptive Testing for LLM Evaluation: A Psychometric Alternative to Static Benchmarks (ATLAS). arXiv:2511.04689.",
        "Liu, J., et al. (2026). Scalable Text-Embedding-informed Cognitive Diagnosis of Large Language Models. arXiv:2603.14676.",
        "Laplace-PSN-IRT: Uncertainty Quantification for Neural IRT Models of LLM Benchmarks. arXiv:2607.25257.",
        "Item Response Scaling Laws. ICML 2026.",
        "Facione, P. A. (1990). Critical Thinking: A Statement of Expert Consensus (Delphi Report). ERIC ED315423.",
    ]
    for ref in refs:
        add_ref(doc, ref)

    out = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/入学测试设计报告_能力画像方案.docx"
    doc.save(out)
    print("saved:", out)


if __name__ == "__main__":
    build()
