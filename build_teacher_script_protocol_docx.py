# -*- coding: utf-8 -*-
"""生成《教师脚本协议设计——基于“引导形成共识”证据链（主线 B）》Word 文档。"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches

from build_report_docx import (
    style_font,
    run_font,
    add_numbering_defs,
    add_list_para,
    make_table,
    add_heading,
    add_body,
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


def add_h2(doc, text):
    return add_heading(doc, text, 2)


def build():
    doc = Document()
    doc.core_properties.title = "教师脚本协议设计——基于“引导形成共识”证据链（主线 B）"

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
    r = first_p.add_run("教师脚本协议设计")
    run_font(r, size=22, bold=True, color=INK_BLUE)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(10)
    rs = sub.add_run("基于“引导形成共识”证据链（主线 B）：Roschelle 收敛 → Mercer 探索型对话 → "
                     "Berkowitz & Gibbs 跨主体推理 → Osborne TAP → Fischer 脚本理论 → Weinberger / Stegmann 对照实验")
    run_font(rs, size=12, color=MUTED)

    for label, value in (
        ("汇报人", "王行杭"),
        ("日期", "2026-08-31"),
        ("任务", "主线 B 证据链 → 教师脚本协议设计"),
        ("状态", "方案（待实验）；关键文献已下载到 06_引导形成共识_教育理论"),
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
        "之前的“教师模型研讨协议”有流程但没有证据链。主线 B 补上了最关键的一块：Weinberger 2010 "
        "用随机对照证明“无脚本小组并不优于个体”——这就是基线三方互评（unscripted group）为什么涨不上去的直接解释；"
        "Fischer 2013 给出脚本五要素，说明为什么单纯加提示词不算脚本。本文把教师模型重新定义为 external script，"
        "给出五阶段流程、transactive 发言协议、TAP 编码字段与三条件消融设计，可直接进入编码。",
    )
    add_body(doc, "", after=2)

    # ---------- 一、设计总纲 ----------
    add_heading(doc, "一、设计总纲：从“加提示词”升级为“完整脚本”", 1)
    add_body(doc, "Weinberger, Stegmann & Fischer (2010) 的三组对照实验结论：脚本化小组超越个体，"
                  "而无脚本小组并不超越个体。也就是说，讨论的收益不是“几个人聚在一起”自动产生的，"
                  "而是来自外部引导结构（script）。我们之前的消融里“只加提示词”效果不稳，"
                  "正是因为提示词没有构成完整脚本——缺阶段、缺角色、缺顺序、缺分布。")
    add_body(doc, "Fischer, Kollar, Stegmann & Wecker (2013) 把脚本拆成五个构成要素，任何一个要素缺失，"
                  "引导结构都不完整。下表直接给出本实验的配置：")
    make_table(
        doc,
        [1.25, 2.0, 1.6],
        ["脚本要素", "本实验配置", "对应原文"],
        [
            ("参与者 participants", "3 个讨论模型 + 教师模型 + 元模型", "Fischer 2013"),
            ("角色 roles", "学生（辩护者/质询者）；教师（主持、不答题、不投票）；元模型（裁决）", "Fischer 2013"),
            ("活动 activities", "独立作答、分歧识别、TAP 提问、transactive 质询、收敛检查", "Stegmann 2007"),
            ("顺序 sequencing", "五阶段固定顺序（见第二节）", "Fischer 2013"),
            ("分布 distribution", "少数派先发言；教师按轮点名，防止多数先入为主", "Mercer 1996"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)

    # ---------- 二、五阶段流程 ----------
    add_heading(doc, "二、五阶段流程（每一步标注证据链出处）", 1)
    make_table(
        doc,
        [1.0, 2.2, 1.7, 1.2],
        ["阶段", "教师动作", "证据链出处", "输出产物"],
        [
            ("1 独立作答", "不干预；沿用基线采样，产出 3 条初始推理链", "对照组前提（Weinberger 2010 的 individual 基线）", "3 条初始链"),
            ("2 分歧识别", "比较 3 条链，输出分歧清单：答案分歧 / 推理冲突 / 事实冲突", "Roschelle 1992 冲突起点", "分歧清单"),
            ("3 探索型启动", "声明规则：公开推理、欢迎被质疑、必须对他人推理操作", "Mercer 1996 探索型对话", "规则声明"),
            ("4 论证循环（≤3 轮）", "TAP 六要素提问 + 交叉质询；每轮发言按结构化字段输出", "Osborne 2004 TAP；Berkowitz & Gibbs 1983", "结构化发言 + 改口记录"),
            ("5 收敛与终止", "论证级一致检查；无新信息；轮次上限", "Roschelle 1992 收敛", "终稿 + 收敛报告"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_body(doc, "与旧协议的区别：旧协议的四阶段来自 van Eemeren 批判性讨论；本版把“探索型对话规则”"
                  "“transactive 判据”“TAP 编码”三个可测量部件嵌入流程，并把终止条件从“多数一致”"
                  "改成“论证级一致”（选项一致但理由矛盾 → 继续讨论）。", after=2)

    # ---------- 三、Transactive 发言协议 ----------
    add_heading(doc, "三、Transactive 发言协议（Berkowitz & Gibbs 1983）", 1)
    add_body(doc, "跨主体推理（transactive reasoning）=“对他人推理进行的推理”：发言必须操作目标模型的推理，"
                  "而不是复述自己的原推理。这是把“交叉质询”从口号变成可执行判据。")
    make_table(
        doc,
        [1.0, 1.7, 2.4],
        ["类型", "定义", "提示词模板"],
        [
            ("澄清型 clarify", "复述并确认对方推理", "“你同意模型 A 的第 2 步吗？先用你自己的话复述它的推理，再表态。”"),
            ("加工型 elaborate", "补充对方推理缺失的条件/步骤", "“模型 A 的推理还缺什么？请补充一个它能成立或失效的限定条件。”"),
            ("批判型 critique", "指出对方推理断裂的一环并说明理由", "“请指出模型 A 推理链中断的那一环，并说明为什么断。”"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_body(doc, "判定规则：若发言只是重复自己的原推理、没有对目标模型推理的任何操作，教师判定为“非 transactive”，"
                  "要求按三类模板重发。过程指标：transactivity 率 = transactive 发言数 / 总发言数，"
                  "期望教师模式下显著高于基线互评。", after=2)

    # ---------- 四、TAP 编码 ----------
    add_heading(doc, "四、TAP 发言质量编码（Osborne, Erduran & Simon 2004）", 1)
    add_body(doc, "每轮发言强制按 Toulmin 六要素输出结构化字段。教师据此判断“谁贡献了新的证据/理由/反驳”，"
                  "而不是“谁说得长”。")
    make_table(
        doc,
        [1.0, 1.8, 2.3],
        ["TAP 字段", "含义", "示例（bad1 肉桂醛碳数题）"],
        [
            ("claim", "结论主张", "“产物是 C。”"),
            ("data", "证据/题干条件", "“肉桂醛分子式 C9H8O。”"),
            ("warrant", "数据→主张的推理依据", "“还原反应只加氢不加碳，碳数守恒。”"),
            ("backing", "规则的支援/适用条件", "“醛的催化加氢不改变碳骨架。”"),
            ("rebuttal", "反驳/替代排除", "“产物不是 D：D 的碳数与原料不符。”"),
            ("qualifier", "限定/边界", "“在标准加氢条件下成立。”"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_body(doc, "质量评分：TAP 完整度 = 已出现字段数 / 6。教师每轮输出各模型完整度；完整度不作为奖励权重，"
                  "只作为过程指标和提问依据（谁缺 warrant 就问谁要 warrant）。", after=2)

    # ---------- 五、对照设计 ----------
    add_heading(doc, "五、与基线的对照设计（Weinberger 2010 实验设计移植）", 1)
    make_table(
        doc,
        [1.15, 2.1, 1.75],
        ["条件", "配置", "作用"],
        [
            ("A 基线（unscripted）", "现有三方互评：pairwise margin + 消息传递", "对照组，即“无脚本小组”"),
            ("B 教师脚本（scripted）", "本协议完整版：五阶段 + transactive + TAP", "实验组，即“脚本化小组”"),
            ("C 半脚本（仅 TAP 提问）", "有 TAP 提问但无 transactive 质询要求", "消融：分离“结构化”与“跨主体”两种机制的贡献"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_body(doc, "主指标：198 题准确率，B vs A 做 McNemar 配对检验（基线 41.41%）。"
                  "过程指标：转对/转错题数、TAP 完整度、transactivity 率、收敛类型（选项级 vs 论证级）。")
    add_body(doc, "实证预期与陷阱：Weinberger 2010 预测 B > A；但 Stegmann 2007 提醒脚本可能只提升论证形式、"
                  "不提升领域知识——若 B 的 TAP 完整度上升而准确率不升，说明形式有了但领域推理没变，"
                  "下一步应改提问内容（往题干事实聚焦）而不是继续加结构。", after=2)

    # ---------- 六、提示词模板 ----------
    add_heading(doc, "六、提示词模板（可直接粘贴到 --teacher_mode）", 1)

    add_h2(doc, "6.1 阶段 3 规则声明（Mercer 探索型对话 + Berkowitz & Gibbs）")
    add_body(doc, "「本轮讨论规则：① 每条发言必须公开推理过程，不能只给结论；② 你的推理可以被质疑，"
                  "质疑是讨论的一部分；③ 每条发言必须针对其他模型的上一条推理——复述它、补充它、或指出它断了哪里；"
                  "④ 禁止只重复自己的原答案。输出格式：Target=模型X，Type=澄清/加工/批判，Content=…」")

    add_h2(doc, "6.2 阶段 4 TAP 六类提问（Osborne 2004）")
    add_body(doc, "「请按 Toulmin 六要素输出你的完整论证：claim（结论）、data（依据的题干条件）、"
                  "warrant（为什么数据能推出结论）、backing（规则适用条件）、rebuttal（如何排除主要替代项）、"
                  "qualifier（限定条件）。缺哪个字段，教师会点名追问。」")

    add_h2(doc, "6.3 阶段 4 交叉质询（Berkowitz & Gibbs 1983）")
    add_body(doc, "「模型 B，模型 A 声称『……』。你同意它的哪一步、不同意哪一步？先用你自己的话复述它的推理，"
                  "再指出它断了哪一环或补上它漏掉的条件。」")

    add_h2(doc, "6.4 阶段 5 收敛检查（Roschelle 1992）")
    add_body(doc, "「请检查：三个模型现在是否在『论证层面』一致——即不仅答案字母相同，而且支撑理由相同或相容？"
                  "若答案一致但理由互相矛盾，说明尚未收敛，继续讨论；否则输出最终答案。」")

    # ---------- 七、理论→机制映射 ----------
    add_heading(doc, "七、理论 → 机制映射表", 1)
    make_table(
        doc,
        [1.7, 1.9, 2.1],
        ["理论（文献）", "核心思想", "本协议对应组件"],
        [
            ("Roschelle (1992)", "共识 = 论证层面收敛", "阶段 5 论证级一致检查 + 终止条件"),
            ("Mercer (1996)", "探索型对话才有效", "阶段 3 规则声明（公开推理、欢迎质疑）"),
            ("Berkowitz & Gibbs (1983)", "跨主体推理是讨论质量判据", "transactive 三类发言模板 + 判定规则"),
            ("Osborne 等 (2004) TAP", "论证质量可编码", "六字段结构化发言 + TAP 完整度指标"),
            ("Fischer 等 (2013)", "脚本五要素，缺一不可", "参与者/角色/活动/顺序/分布配置表"),
            ("Weinberger 等 (2010)", "脚本化 > 无脚本 ≈ 个体", "三条件对照设计（A/B/C）"),
            ("Stegmann 等 (2007)", "脚本提升形式≠提升内容", "主指标锁定准确率，TAP 仅作过程指标"),
            ("Kuhn & Crowell (2011)", "论证是可训练的", "多轮论证轮次（≤3 轮）设计"),
        ],
        first_col_bold=True,
    )

    # ---------- 八、风险与反措施 ----------
    add_heading(doc, "八、风险与反措施", 1)
    add_list_para(doc, "过度脚本化（over-scripting，Fischer 2013）：脚本过强会限制模型自主探索。"
                       "反措施：反馈分级 L1–L4，L4（给机理线索）少用；轮次上限默认 3。", 110)
    add_list_para(doc, "只升形式不升内容（Stegmann 2007 教训）：TAP 完整度上升但准确率不动。"
                       "反措施：主指标必须是准确率与转对率；若出现该模式，改提问内容而非加结构。", 110)
    add_list_para(doc, "教师自身判断错误：教师不答题、不投票、不直接给答案；必要时换更强裁判，"
                       "教师输出只用于组织讨论与记录，最终裁决仍在元模型。", 110)

    # ---------- 九、参考文献 ----------
    add_heading(doc, "九、参考文献（主线 B 新增，已下载见 06 文件夹）", 1)
    for ref in [
        "Roschelle, J. (1992). Learning by collaborating: Convergent conceptual change. Journal of the Learning Sciences, 2(3), 235–276.（付费，待获取）",
        "Mercer, N. (1996). The quality of talk in children's collaborative activity in the classroom. Learning and Instruction, 6(4), 359–377.（付费，待获取）",
        "Berkowitz, M. W., & Gibbs, J. C. (1983). Measuring the developmental features of moral discussion. Merrill-Palmer Quarterly, 29(4), 399–410.（付费，待获取）",
        "Osborne, J., Erduran, S., & Simon, S. (2004). Enhancing the quality of argumentation in school science. Journal of Research in Science Teaching, 41(10), 994–1020.（已下载）",
        "Kuhn, D., & Crowell, A. (2011). Dialogic argumentation as a vehicle for developing young adolescents' thinking. Psychological Science, 22(4), 545–552.（ERIC 会议版已下载）",
        "Asterhan, C. S. C., & Schwarz, B. B. (2016). Argumentation for learning: Well-trodden paths and unexplored territories. Educational Psychologist, 51(2), 164–187.（付费，待获取）",
        "Fischer, F., Kollar, I., Stegmann, K., & Wecker, C. (2013). Toward a script theory of guidance in computer-supported collaborative learning. Educational Psychologist, 48(1), 56–66.（已下载）",
        "Weinberger, A., Stegmann, K., & Fischer, F. (2010). Learning to argue online: Scripted groups surpass individuals (unscripted groups do not). Computers in Human Behavior, 26(4), 506–515.（已下载）",
        "Stegmann, K., Weinberger, A., & Fischer, F. (2007). Facilitating argumentative knowledge construction with computer-supported collaboration scripts. International Journal of Computer-Supported Collaborative Learning, 2(4), 421–447.（已下载）",
    ]:
        add_ref(doc, ref)

    out = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/教师脚本协议设计_主线B证据链版.docx"
    doc.save(out)
    print("saved:", out)


if __name__ == "__main__":
    build()
