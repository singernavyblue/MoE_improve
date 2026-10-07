# -*- coding: utf-8 -*-
"""生成《教师模型引导式研讨协议——设计方案》Word 文档。"""

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


def build():
    doc = Document()
    doc.core_properties.title = "教师模型引导式研讨协议设计方案"

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
    r = first_p.add_run("教师模型引导式研讨协议——设计方案")
    run_font(r, size=22, bold=True, color=INK_BLUE)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(10)
    rs = sub.add_run("基于 Vygotsky 脚手架 · 苏格拉底式提问 · van Eemeren 批判性讨论 · Toulmin 论证结构")
    run_font(rs, size=13, color=MUTED)

    for label, value in (
        ("汇报人", "王行杭"),
        ("日期", "2026-08-30"),
        ("任务", "教师模型提问协议设计（方向二）"),
        ("状态", "方案（待实验）"),
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
        "把现有“平行各说各话”的消息传递，升级为“教师主持的苏格拉底式研讨”：教师模型按批判性讨论四阶段组织流程，"
        "用 Toulmin 六类问题逐轮追问，按脚手架原则只给“恰好够用”的线索，最终按自定义终止条件收敛，再由元模型裁决。"
        "目标：让模型在引导下暴露盲区、自我修正，而不是互相确认错误。",
    )
    add_body(doc, "", after=2)

    # ---------- 一、机制总览 ----------
    add_heading(doc, "一、机制总览", 1)
    add_body(doc, "三个角色，职责分明：")
    add_list_para(doc, "讨论模型（3 个节点，即现有采样结果）：作为“学生”，回答问题、接受质询、给出中间结论。", 110)
    add_list_para(doc, "教师模型（Prometheus，必要时换更强模型）：主持讨论——识别分歧、组织议题、追问、反馈。教师不答题、不投票。", 110)
    add_list_para(doc, "元模型（qwen）：记录全程、判断收敛、最终裁决（控制权在己方）。", 110)
    add_body(doc, "教师只做四件事：识别分歧 → 组织议题 → 追问中间结论 → 反馈验证线索。整个流程按批判性讨论四阶段组织。", italic=True)

    # ---------- 二、五阶段流程 ----------
    add_heading(doc, "二、五阶段流程", 1)
    add_list_para(doc, "摸底（可选）：入学测试建立能力基线，可注入画像先验（已单独设计方案）。", 12, lead="阶段 0 · ")
    add_list_para(doc, "对抗（分歧识别）：各模型独立作答；教师比较 3 份回答，输出“分歧清单”——答案分歧 / 推理冲突 / 事实冲突。", 12, lead="阶段 1 · ")
    add_list_para(doc, "开局（规则与议题）：教师声明讨论规则（必须给出中间结论、禁止只重复结论），给持有不同答案的模型分配辩护角色，并指定少数派先发言。", 12, lead="阶段 2 · ")
    add_list_para(doc, "论证（提问循环，默认最多 3 轮）：教师按苏格拉底提问模板逐轮追问，穿插交叉质询与分级反馈（详见第三、四节）。", 12, lead="阶段 3 · ")
    add_list_para(doc, "结论（收敛与裁决）：教师汇总各模型改口记录与剩余分歧；满足终止条件即结束；进入池化，由元模型做最终裁决。", 12, lead="阶段 4 · ")

    # ---------- 三、提问协议 ----------
    add_heading(doc, "三、苏格拉底提问协议（Toulmin 六要素）", 1)
    add_body(doc, "教师的提问全部来自一套固定模板，每个模板对应一个 Toulmin 要素，直接针对已实测的失败模式：")
    make_table(
        doc,
        [1.2, 1.3, 2.8, 1.2],
        ["问题类型", "Toulmin 要素", "模板示例", "针对的失败模式"],
        [
            ("澄清型", "Claim", "“你的最终答案具体是？它回答的是题目真正问的类型吗？”", "bad2 except 反题"),
            ("证据型", "Data", "“这一步依赖哪个事实/条件/规则？请引用题干信息。”", "编造事实"),
            ("推理型", "Warrant", "“为什么这些数据能推出这个结论？推理依据是什么？”", "长而空洞的链"),
            ("支援型", "Backing", "“这个反应规则有例外或适用条件吗？”", "过度自信"),
            ("限定词型", "Qualifier", "“你的结论在所有条件下都成立，还是有限定？”", "绝对化断言"),
            ("反驳型", "Rebuttal", "“请给出一个反例，或说明你如何排除主要替代选项。”", "盲点与漏判"),
            ("一致型", "Consistency", "“你的结论与你第 X 步的推理一致吗？请重新检查。”", "bad1 qwen 自相矛盾"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_rich(
        doc,
        [
            ("交叉质询规则：", {"bold": True}),
            ("教师把 A 的中间结论抛给 B：“B，A 声称……你同意吗？依据是什么？”让每个模型从他人视角检验自己的推理；"
             "少数派先发言，防止多数意见先入为主（针对 bad3 从众）。", {}),
        ],
    )

    # ---------- 四、反馈与脚手架 ----------
    add_heading(doc, "四、反馈信息与脚手架分级（Vygotsky ZPD）", 1)
    add_body(doc, "教师的反馈只给“恰好够用”的线索，从最弱一级开始，模型无法自我修正才逐级加强；教师绝不直接给最终答案。")
    make_table(
        doc,
        [0.7, 1.4, 1.8, 2.6],
        ["级别", "名称", "教师做什么", "示例"],
        [
            ("L1", "提示注意", "提醒被忽略的条件/证据", "“你漏掉了题干第 2 个条件。”"),
            ("L2", "指出矛盾", "指出结论与推理/事实冲突", "“你的结论与你算出的 8 个碳矛盾。”"),
            ("L3", "引导验证", "指示重新计算/重查步骤", "“请重数碳原子并对照四个选项。”"),
            ("L4", "参考锚", "给出机理/规则线索（最接近答案）", "“回顾该反应的标准机理，注意立体选择性。”"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_rich(
        doc,
        [
            ("反馈分三类：", {"bold": True}),
            ("事实性反馈（事实错误）、逻辑性反馈（推理断裂）、一致性反馈（结论与推理矛盾）——对应 Facione 三项检查。", {}),
        ],
    )

    # ---------- 五、终止条件 ----------
    add_heading(doc, "五、终止条件（van Eemeren 结论阶段）", 1)
    make_table(
        doc,
        [1.0, 5.5],
        ["条件", "说明"],
        [
            ("1 分歧清零", "所有初始分歧点均已被回应"),
            ("2 无新信息", "连续两轮无模型改口且无新证据"),
            ("3 轮次上限", "默认 3 轮（可调）"),
            ("4 共识置信度", "教师判断多数一致且论证自洽"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=4)

    # ---------- 六、防从众 ----------
    add_heading(doc, "六、防从众与防谄媚规则", 1)
    add_list_para(doc, "改口必须说明采纳了哪条具体反馈；坚持原答案必须解释为何反馈不成立。", 110)
    add_list_para(doc, "教师随机点名少数派先发言，防止多数意见先入为主。", 110)
    add_list_para(doc, "教师反馈只评“论证质量”，不评“立场对错”，避免诱导。", 110)

    # ---------- 七、对接 ----------
    add_heading(doc, "七、与现有管线的对接", 1)
    add_list_para(doc, "替换点：S→T / T→S 消息传递 → 教师主持的交叉质询循环；边构建保持 pairwise margin 不变。", 110)
    add_list_para(doc, "教师模型：prometheus（8192 上下文）；如需更强可换 meta 模型或 DeepSeek API。", 110)
    add_list_para(doc, "池化：保持 mean pooling 或加权投票；元模型 qwen 做最终裁决。", 110)
    add_list_para(doc, "改动：modules.py 新增 teacher_rounds 流程；main.py 增加 --teacher_mode 开关。", 110)

    # ---------- 八、度量 ----------
    add_heading(doc, "八、效果度量与消融设计", 1)
    add_list_para(doc, "主指标：全量 198 题准确率 vs 基线 41.41%。", 110)
    add_list_para(doc, "过程指标：讨论前后改对率/改错率、共识收敛率、有效提问率（提问后模型改口且改对的占比）。", 110)
    add_list_para(doc, "消融：A 只提问不反馈；B 只反馈不交叉质询；C 完整教师模式；对照基线。", 110)

    # ---------- 九、理论映射 ----------
    add_heading(doc, "九、理论 → 机制组件映射", 1)
    make_table(
        doc,
        [1.6, 2.0, 2.9],
        ["理论", "核心思想", "本方案对应组件"],
        [
            ("Vygotsky 脚手架", "在引导下达到独自达不到的水平", "四级反馈（L1–L4），只给恰好够用的线索"),
            ("苏格拉底式提问", "引导式提问提升批判性思维", "七类问题模板 + 交叉质询"),
            ("van Eemeren 批判性讨论", "四阶段 + 终止条件", "对抗→开局→论证→结论 + 4 条终止条件"),
            ("Toulmin 论证结构", "完整论证六要素", "提问模板的要素标注（Data/Warrant/Rebuttal 等）"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=4)

    # ---------- 参考文献 ----------
    add_heading(doc, "十、参考文献", 1)
    for ref in [
        "Vygotsky, L. S. (1978). Mind in Society: The Development of Higher Psychological Processes. Harvard University Press.",
        "van Eemeren, F. H., & Grootendorst, R. (2004). A Systematic Theory of Argumentation: The Pragma-Dialectical Approach. Cambridge University Press.",
        "Toulmin, S. E. (1958). The Uses of Argument. Cambridge University Press.",
        "Facione, P. A. (1990). Critical Thinking: A Statement of Expert Consensus (Delphi Report). ERIC ED315423.",
        "Paul, R., & Elder, L. (2007). Critical Thinking: Learn the Tools the Best Thinkers Use. Pearson.（苏格拉底式提问六类问题分类）",
    ]:
        add_ref(doc, ref)

    out = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/教师模型引导式研讨协议_设计方案.docx"
    doc.save(out)
    print("saved:", out)


if __name__ == "__main__":
    build()
