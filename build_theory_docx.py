# -*- coding: utf-8 -*-
"""生成《评估标准理论溯源报告》Word 文档。"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
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

EAST = "PingFang SC"
INK_BLUE = RGBColor(0x0B, 0x25, 0x45)
MUTED = RGBColor(0x59, 0x59, 0x59)


def add_h2(doc, text):
    return add_heading(doc, text, 2)


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
    doc.core_properties.title = "评估标准理论溯源报告"

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
    footer = section.footer
    fp = footer.paragraphs[0]
    fp.paragraph_format.space_before = Pt(0)
    fp.paragraph_format.space_after = Pt(0)
    add_page_number(fp)

    # ---------- 首屏 ----------
    first_p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    first_p.paragraph_format.space_before = Pt(0)
    first_p.paragraph_format.space_after = Pt(2)
    r = first_p.add_run("评估标准理论溯源报告")
    run_font(r, size=22, bold=True, color=INK_BLUE)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(10)
    rs = sub.add_run("“选更完整且无错误的推理链”——教育学与测量学依据")
    run_font(rs, size=13, color=MUTED)

    for label, value in (
        ("汇报人", "王行杭"),
        ("日期", "2026-08-28"),
        ("任务", "P0 · 评估标准理论溯源"),
        ("状态", "完成"),
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

    # ---------- 一、结论速览 ----------
    add_callout(
        doc,
        "结论速览",
        "“选更完整且无错误的推理链”不是主观直觉，而是四条成熟学科主线的交汇："
        "① 比较判断测量学（Thurstone、Pollitt）为“两两比较选更好”提供可靠性保证；"
        "② 论证结构理论（Toulmin）与 SOLO 分类学定义“更完整”；"
        "③ 批判性思维评估（Facione）定义“无错误”；"
        "④ 建构主义与社会建构主义说明为什么评推理过程、以及如何通过引导式讨论形成共识。",
    )
    add_body(doc, "", after=2)

    # ---------- 二、判断标准的拆解 ----------
    add_heading(doc, "一、判断标准的三层拆解", 1)
    add_body(
        doc,
        "“选更完整且无错误的推理链”可以拆成四个成分，每一个成分都有对应的学科问题与原始理论：",
    )
    make_table(
        doc,
        [1.5, 2.2, 2.8],
        ["判断成分", "要回答的问题", "对应理论"],
        [
            ("“更完整”", "什么样的推理算结构完整？", "Toulmin 论证结构；SOLO 学习结果结构；ECD 模型阐述"),
            ("“无错误”", "什么样的推理算有效可靠？", "逻辑有效性（soundness）；Facione 批判性思维评估"),
            ("“选”（比较排序）", "怎样比较才能保证可靠？", "比较判断理论：Thurstone 1927；Bradley–Terry 1952；Pollitt ACJ 2012"),
            ("“推理链”（评估对象）", "为什么评过程而不是只看结论？", "建构主义；Novak & Gowin 概念图；Mislevy 证据中心设计"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=4)

    # ---------- 三、理论依据详述 ----------
    add_heading(doc, "二、理论依据详述", 1)

    add_h2(doc, "2.1 比较判断理论——“选”的测量学背书（核心）")
    add_rich(
        doc,
        [
            ("Thurstone（1927）", {"bold": True}),
            ("《A Law of Comparative Judgment》：提出“比较判断法则”，证明人对“哪个更好”的定性比较（包括教育作品中优劣的比较）可以在心理尺度上量化，并可通过内部一致性检验。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Bradley & Terry（1952）", {"bold": True}),
            ("：把两两比较结果转换为可估计的尺度值（BT 模型）——“赢得越多、赢得越强，得分越高”，这是比较判断走向量化的标准数学形式。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Pollitt（2012）", {"bold": True}),
            ("《The Method of Adaptive Comparative Judgement》：教育评估中，评分者只回答“哪个更好”，再用 BT 模型聚合出量表；ACJ 达到的信度往往高于细致的评分量表。论文原意（翻译）：“评分者只需做出‘有效’的质量判断，而 ACJ 能达到极高的信度，通常高于可实际操作的评分标记。”", {}),
        ],
    )
    add_h2(doc, "与本实验的映射")
    add_list_para(
        doc,
        "我们的 pairwise margin 裁判 = ACJ 的简化版：对每对模型推理链做两两比较并加权幅度。",
        110,
    )
    add_list_para(
        doc,
        "“85% 分差≤1”的问题正是 ACJ 要解决的：不依赖绝对分值，而从大量两两比较中统计估计尺度。",
        110,
    )
    add_list_para(
        doc,
        "改进方向（理论指引）：用 BT 模型估计每条链的尺度值（而非手写公式），并借鉴 ACJ 的自适应选题设计比较对。",
        110,
    )

    add_h2(doc, "2.2 论证结构理论——“更完整”的构成（Toulmin 1958）")
    add_body(
        doc,
        "《The Uses of Argument》给出完整论证的六要素，论证“完整”不是字数多，而是要素是否齐全：",
    )
    make_table(
        doc,
        [1.8, 4.7],
        ["要素", "含义"],
        [
            ("主张（Claim）", "要证明的结论"),
            ("数据（Data）", "支持结论的事实依据"),
            ("正当理由（Warrant）", "为什么数据能推出结论的推理依据"),
            ("支援（Backing）", "对正当理由本身的支撑"),
            ("限定词（Qualifier）", "结论的强度限定（通常/可能）"),
            ("反驳（Rebuttal）", "例外情况与反例"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_list_para(
        doc,
        "映射：rubric 的“信息利用”对应数据与正当理由；“结果验证”对应结论与证据一致性；“冗长但错误的链”正是只有主张和大量无关数据、正当理由不成立的典型。",
        110,
    )

    add_h2(doc, "2.3 SOLO 分类学——“更完整”的层级（Biggs & Collis 1982）")
    add_body(
        doc,
        "SOLO（Structure of the Observed Learning Outcome）把学习结果的结构分成五级，天然对应“更完整”的档位：",
    )
    make_table(
        doc,
        [1.8, 4.7],
        ["层级", "表现"],
        [
            ("前结构", "答非所问，信息无关"),
            ("单点结构", "只抓住一个相关要点"),
            ("多点结构", "罗列多个要点，但未建立联系"),
            ("关联结构", "要点之间形成联系，构成整体"),
            ("抽象拓展", "在关联基础上泛化到新情境"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_list_para(
        doc,
        "映射：1~5 分推理链档位 ≈ SOLO 层级——1 分≈前结构；2 分≈单点/多点但结论错；3 分≈多点且结论对但缺关联；4 分≈关联结构；5 分≈关联＋抽象拓展。这给“更完整”一个可操作的分级描述。",
        110,
    )

    add_h2(doc, "2.4 批判性思维评估——“无错误”的标准（Facione 1990）")
    add_body(
        doc,
        "《德尔斐报告》（Facione, 1990, ERIC ED315423）由跨学科专家达成共识，给出批判性思维的六项认知技能：解释、分析、评估、推论、说明、自我调节。",
    )
    add_list_para(
        doc,
        "“无错误”≈ 评估（判断主张是否可信）＋分析（识别论据结构与错误）；“说明”对应要求推理链讲清理由；“自我调节”对应教师模型追问逼出的自我修正。",
        110,
    )
    add_list_para(
        doc,
        "逻辑学上，论证可靠（sound）需要同时满足“形式有效（valid）”且“前提为真”——这是“无错误”最严格的定义。",
        110,
    )

    add_h2(doc, "2.5 建构主义与过程评估——为什么评推理链")
    add_rich(
        doc,
        [
            ("建构主义（Piaget、von Glasersfeld）", {"bold": True}),
            ("：理解是学习者主动建构的，结论对不等于理解对（可能靠巧合或记忆）；评估应探测深层理解而非只核对答案。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Novak & Gowin（1984）", {"bold": True}),
            ("：用概念图评估知识关联的完整度，开创“以结构完整性评估理解”的先河。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Mislevy 等（2003）证据中心设计（ECD）", {"bold": True}),
            ("：评估 = 从证据推断能力，“推理过程质量”就是能力的证据。", {}),
        ],
    )
    add_list_para(
        doc,
        "映射：这正是“看推理链而不只看答案字母”的理由，也解释了 bad case“结论对但推理错（靠误差抵消）”为什么必须扣分。",
        110,
    )

    add_h2(doc, "2.6 社会建构主义与引导式讨论——教师模型的理论基础")
    add_rich(
        doc,
        [
            ("Vygotsky（1978）", {"bold": True}),
            ("：最近发展区（ZPD）、语言中介与脚手架（scaffolding）——在他人引导下可以达到独自达不到的水平，是“教师模型提问引导模型形成共识”的直接理论。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Scardamalia & Bereiter（1994）", {"bold": True}),
            ("：知识建构社区与进步性话语——通过讨论改进知识，而非简单投票聚合。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("van Eemeren & Grootendorst（2004）", {"bold": True}),
            ("：批判性讨论四阶段（对抗、开局、论证、结论）＋十条讨论规则——为“什么时候结束讨论”提供正式框架，对应“终止条件由我们自定义”。", {}),
        ],
    )
    add_rich(
        doc,
        [
            ("Alfieri 等（2013）元分析", {"bold": True}),
            ("：案例对比学习（Learning through Case Comparisons）显著提升学习效果——导师所说的“对比学习”有实验证据。", {}),
        ],
    )
    add_list_para(
        doc,
        "苏格拉底式提问：引导式提问是提升批判性思维与论证质量的教学方法，是“师生式深度提问”的教育学原型。",
        110,
    )

    # ---------- 四、四维 rubric 对应 ----------
    add_heading(doc, "三、四维标准与理论的对应", 1)
    make_table(
        doc,
        [1.5, 2.4, 2.6],
        ["四维", "理论源头", "检查要点"],
        [
            ("目标对齐", "Facione 解释/分析；ECD 任务模型", "推理是否针对题目要求（如 except 题是否理解“选错误项”）"),
            ("效率", "Toulmin 相关性；SOLO", "是否冗余、离题，把长度当深度"),
            ("信息利用", "Toulmin 数据/正当理由/支援", "证据是否正确、是否给出推理依据"),
            ("结果验证", "Facione 评估；逻辑有效性", "结论是否正确、与证据是否一致"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_rich(
        doc,
        [
            ("现代应用印证：", {"bold": True}),
            ("LLM 评估中的过程监督（process supervision, Lightman et al., 2023）也独立得出同一结论——对推理每一步打分优于只看最终答案，与上述教育学理论互为印证。", {}),
        ],
    )

    # ---------- 五、启示 ----------
    add_heading(doc, "四、对本实验的可操作启示", 1)
    add_list_para(
        doc,
        "pairwise 比较本身有测量学背书，问题不在“两两比较”，而在聚合方式：用 Bradley–Terry 估计每条链的尺度值，替代手写 margin 公式。",
        110,
    )
    add_list_para(
        doc,
        "“完整”评分改为 SOLO 五级描述，给裁判一个“结构档位”，而不是模糊的“更完整”。",
        110,
    )
    add_list_para(
        doc,
        "教师模型的提问类型按 Toulmin 六要素设计：问数据（你的依据是什么？）、问正当理由（为什么数据能推出结论？）、问反驳（有没有反例？）。",
        110,
    )
    add_list_para(
        doc,
        "讨论终止条件参考 pragma-dialectics 四阶段与规则：所有分歧点均被回应、连续两轮无新信息、达到轮次上限等。",
        110,
    )
    add_list_para(
        doc,
        "入学测试（能力基线）衔接 IRT 与能力画像（另文），此处不再展开。",
        110,
    )

    # ---------- 六、参考文献 ----------
    add_heading(doc, "五、参考文献", 1)
    refs = [
        "Thurstone, L. L. (1927). A law of comparative judgment. Psychological Review, 34(4), 273–286.",
        "Bradley, R. A., & Terry, M. E. (1952). Rank analysis of incomplete block designs: I. The method of paired comparisons. Biometrika, 39(3–4), 324–345.",
        "Pollitt, A. (2012). The method of Adaptive Comparative Judgement. Assessment in Education: Principles, Policy & Practice, 19(3), 281–300.",
        "Toulmin, S. E. (1958). The Uses of Argument. Cambridge University Press.",
        "Biggs, J. B., & Collis, K. F. (1982). Evaluating the Quality of Learning: The SOLO Taxonomy. Academic Press.",
        "Facione, P. A. (1990). Critical Thinking: A Statement of Expert Consensus for Purposes of Educational Assessment and Instruction (Delphi Report). ERIC ED315423.",
        "Vygotsky, L. S. (1978). Mind in Society: The Development of Higher Psychological Processes. Harvard University Press.",
        "Novak, J. D., & Gowin, D. B. (1984). Learning How to Learn. Cambridge University Press.",
        "Scardamalia, M., & Bereiter, C. (1994). Computer support for knowledge-building communities. Journal of the Learning Sciences, 3(3), 265–283.",
        "van Eemeren, F. H., & Grootendorst, R. (2004). A Systematic Theory of Argumentation: The Pragma-Dialectical Approach. Cambridge University Press.",
        "Mislevy, R. J., Steinberg, L. S., & Almond, R. G. (2003). On the structure of educational assessments. Measurement, 1(1), 3–62.",
        "Alfieri, L., Nokes-Malach, T. J., & Schunn, C. D. (2013). Learning through case comparisons: A meta-analytic review. Educational Psychologist, 48(2), 87–113.",
        "Brookhart, S. M. (2013). How to Create and Use Rubrics for Formative Assessment and Grading. ASCD.",
    ]
    for ref in refs:
        add_ref(doc, ref)

    out = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/评估标准理论溯源报告.docx"
    doc.save(out)
    print("saved:", out)


if __name__ == "__main__":
    build()
