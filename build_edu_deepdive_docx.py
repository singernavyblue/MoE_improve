# -*- coding: utf-8 -*-
"""生成《教育理论深挖：构建联系 × 引导形成共识》Word 文档。"""

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
    doc.core_properties.title = "教育理论深挖：构建联系 × 引导形成共识"

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
    r = first_p.add_run("教育理论深挖：构建联系 × 引导形成共识")
    run_font(r, size=22, bold=True, color=INK_BLUE)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(10)
    rs = sub.add_run("导师重点两条主线 · 从“能引用的理论”到“能落地的部件”")
    run_font(rs, size=13, color=MUTED)

    for label, value in (
        ("汇报人", "王行杭"),
        ("日期", "2026-08-31"),
        ("任务", "深挖“构建联系”与“引导形成共识”两条教育理论主线"),
        ("状态", "17 篇新增文献，出处已核实"),
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
        "两条主线各有一条“文献证据链”：构建联系 = Ausubel 有意义学习 → Novak 概念图 → "
        "Linn & Eylon 知识整合（KIS 评分）→ Gentner 结构映射；引导形成共识 = Roschelle 收敛性概念变化 → "
        "Mercer 对话类型 → Berkowitz & Gibbs 跨主体推理 → Fischer 协作脚本理论（含随机对照实验证据）。"
        "每条链都能落到教师模型或四维 rubric 的一个具体部件上。",
    )
    add_body(doc, "", after=2)

    # ---------- 一、总览 ----------
    add_heading(doc, "一、总览：两条主线 × 理论层次 × 文献 × 可落地部件", 1)
    make_table(
        doc,
        [1.35, 1.75, 1.9, 1.6],
        ["主线", "理论层次", "关键文献", "可落地部件"],
        [
            ("A 构建联系", "A1 有意义学习（锚定已有认知结构）", "Ausubel (1968)", "Q 矩阵 = 知识点锚定关系；画像先验"),
            ("A 构建联系", "A2 概念图（把联系外显为命题网络）", "Novak & Gowin (1984)", "D4 结构深度 = 命题连接密度"),
            ("A 构建联系", "A3 知识整合（观点库 → 整合排序）", "Linn & Eylon (2011); Liu 等 (2008)", "裁判“整合度”评分，仿 KIS 0–5"),
            ("A 构建联系", "A4 类比与结构映射（比较中提取共同结构）", "Gentner (1983); Gick & Holyoak (1983)", "pairwise 比较 = 结构映射"),
            ("B 引导共识", "B1 收敛性概念变化（协商收敛）", "Roschelle (1992)", "终止条件 = 论证级共识而非选项一致"),
            ("B 引导共识", "B2 对话类型（争执/累积/探索）", "Mercer (1996)", "教师强制把对话推向探索型"),
            ("B 引导共识", "B3 跨主体推理（操作他人推理）", "Berkowitz & Gibbs (1983)", "交叉质询的“transactive”判据"),
            ("B 引导共识", "B4 论证教学与质量编码", "Osborne 等 (2004); Asterhan & Schwarz (2016)", "TAP 元素编码每轮发言"),
            ("B 引导共识", "B5 协作脚本理论（外部引导）", "Fischer 等 (2013); Weinberger 等 (2010)", "教师模型 = external script 的实证依据"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=4)

    # ---------- 二、主线 A ----------
    add_heading(doc, "二、主线 A：构建联系（Knowledge Integration & Connection Building）", 1)
    add_body(
        doc,
        "导师原话指向“评估知识正确性及构建联系方面有成熟理论”。这一条线的成熟度其实超过预期："
        "教育心理学不仅有“知识是联系的网络”这种比喻，还有一整套可操作的评估方法（概念图评分、"
        "知识整合评分 KIS），这正是我们 Q 矩阵与四维 rubric 缺的理论底座。",
    )

    add_h2(doc, "2.1 A1 有意义学习理论（Ausubel）——为什么“联系”是评估对象")
    add_body(doc, "核心：新知识只有锚定（anchoring）进学习者已有的认知结构才算有意义学习；孤立记忆是机械学习。"
                  "评估的应当是“新知识是否挂到了正确的旧知识上”，而不是“这条知识本身背没背对”。")
    add_list_para(doc, "→ 对实验 1：Q 矩阵正是“知识点锚定关系”的显式形式——每道题列出的能力属性（D1–D5）"
                       "相当于该题要求模型“调用并连接”的知识点集合。", 110)
    add_list_para(doc, "→ 对实验 2：画像先验（“四则运算掌握好 → 复杂数学答对率高”）在 Ausubel 框架下就是"
                       "“低层知识点是否锚定好”的可观测证据——和 Leighton 属性层次模型（能力画像方向已有）完全同构。", 110)

    add_h2(doc, "2.2 A2 概念图（Novak & Gowin 1984；Novak 1990）——把“联系”变成可评分对象")
    add_body(doc, "核心：概念图把知识结构外显为“概念—连接词—命题”的三元网络；评估时不再数概念个数，"
                  "而是检查命题（两两概念之间带连接词的完整陈述）是否有效、层级是否清晰。")
    add_list_para(doc, "→ 对实验：D4 结构深度可以从“文本长短”升级为“命题连接密度”——一条好的推理链"
                       "等价于一张小的概念图：每一步是“证据 → 所以 → 结论”的命题边。裁判可以明确检查"
                       "“这条链的中间命题是否把题干条件与结论连成一条无断点的路径”。", 110)
    add_list_para(doc, "实证提醒：McClure, Sonak & Suen (1999) 对比了 6 种概念图评分法，信度 r = .23–.76，"
                       "结论是“连接数量”≠“连接质量”，结构分必须结合“是否接近标准图（master map）”。"
                       "对应我们：不要因为某条链“步骤多”就给高分——这正是 400 错误中“冗长错误链骗高分”的理论镜像。", 110)

    add_h2(doc, "2.3 A3 知识整合框架（Linn & Eylon）与 KIS 评分（Liu 等 2008）——裁判评分的直接原型")
    add_body(doc, "核心：学习者头脑中不是一个“正确版本”，而是一个观点库（repertoire of ideas）；"
                  "学习 = 把新观点与旧观点建立联系、比较证据、排序、取舍。知识整合（Knowledge Integration）"
                  "因此是潜变量，评估用 KIS（Knowledge Integration Scoring）0–5 量表：从“只有孤立观点”"
                  "逐级到“多观点建立联系并区分强弱”。")
    make_table(
        doc,
        [1.2, 3.4],
        ["KIS 档位", "含义（对应到推理链）"],
        [
            ("1 分", "只有孤立/错误观点，无联系（= 空泛或自相矛盾的链）"),
            ("2 分", "有联系但建立在错误前提上（= 内部自洽但前提错）"),
            ("3 分", "正确观点与错误观点并存，未整合（= bad1：结论对但“10 个碳”错误并存）"),
            ("4 分", "主要观点正确、联系基本成立，小缺口"),
            ("5 分", "观点全部正确且整合成完整论证（= 与参考链等价）"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "关键点：KIS 明确把“正确观点与错误观点并存、未整合”单独设为一档（3 分）——"
                  "这正是我们 bad1（结论对、推理含实质错误）的理论地位：不是“半对半错”，而是“未完成知识整合”。", after=2)
    add_list_para(doc, "→ 对实验：可以把裁判的评分锚点从“事实对错”扩展为“整合度”：分数档 = KIS 五级，"
                       "每条链先问“有哪些观点”再问“是否建立了联系、是否区分了强弱”。", 110)

    add_h2(doc, "2.4 A4 类比与结构映射（Gentner 1983；Gick & Holyoak 1983）——pairwise 比较的理论根基")
    add_body(doc, "核心：类比迁移的不是表面特征，而是关系结构（structure-mapping，系统性原则）；"
                  "Gick & Holyoak 进一步证明：给两个不同类比例子比给一个例子更容易归纳出抽象图式（schema induction）。")
    add_list_para(doc, "→ 对实验 1：pairwise 裁判的本质就是“让裁判比较两条链、提取共同结构”——"
                       "Gentner 说明为什么这种比较有效：它在迫使裁判对齐“关系层”而不是“表面层”。", 110)
    add_list_para(doc, "→ 对实验 2：Alfieri 等 (2013) 的元分析（案例对比学习）与 Chi (2009) ICAP"
                       "（交互 > 建构 > 主动 > 被动）正好衔接：比较 + 交互 = 最强的学习/评估形态。", 110)

    # ---------- 三、主线 B ----------
    add_heading(doc, "三、主线 B：引导形成共识（Guided Consensus Formation）", 1)
    add_body(
        doc,
        "导师原话指向“通过讨论引导形成共识的科学方法”，且明确批评当前机制是“无组织小组讨论”。"
        "这一条线最关键的实证结论：无引导的小组讨论在大量对照实验中并不优于个人——"
        "收益来自引导结构（script），这正是教师模型存在的理由。",
    )

    add_h2(doc, "3.1 B1 收敛性概念变化（Roschelle 1992）——共识的目标定义")
    add_body(doc, "核心：协作学习的本质是“收敛性概念变化”（convergent conceptual change）——参与者通过"
                  "冲突→协商→再表述，把各自的概念收敛成共享理解。收敛 ≠ 少数服从多数，而是“共同理解的达成”。")
    add_list_para(doc, "→ 对实验：教师模型的终止条件不应是“选项一致”，而应是“论证级收敛”："
                       "各方是否在证据与推理层面达成一致。若只是答案字母一致而理由矛盾，应继续追问。", 110)

    add_h2(doc, "3.2 B2 对话类型（Mercer 1996）——什么样的讨论才有效")
    add_body(doc, "核心：课堂对话分三类——争执型（disputational：各说各话、防御性）、"
                  "累积型（cumulative：不加批判地附和）、探索型（exploratory：公开推理、相互质疑、建设性批判）。"
                  "只有探索型对话能产生高质量共识。")
    add_list_para(doc, "→ 对实验：基线三方互评的失败模式（bad3 谄媚从众）在 Mercer 框架下就是“争执型/累积型”混杂物——"
                       "A 们没有公开推理、B 被说服时也没有得到可检验的理由。教师模型的职责是强制把对话类型"
                       "切成探索型：要求发言“公开推理 + 给理由 + 可被质疑”。", 110)

    add_h2(doc, "3.3 B3 跨主体推理（Berkowitz & Gibbs 1983）——教师质询的判据")
    add_body(doc, "核心：transactive reasoning = “对他人推理进行的推理”（clarify / elaborate / critique / refute 对方观点）。"
                  "有效讨论中，高质量发言是对同伴推理的加工，而不是自说自话。")
    add_list_para(doc, "→ 对实验：给教师模型的“交叉质询”一个可操作的判定标准——当教师追问时，"
                       "要求模型回答必须 transact 目标模型刚才的推理（例如“你的第 2 步基于 X，但 X 只在 Y 条件下成立”），"
                       "而不是复述自己的原推理。这正是从“平行辩论”到“师生问答”的机制化定义。", 110)

    add_h2(doc, "3.4 B4 论证教学与论证质量编码（Osborne 等 2004；Kuhn & Crowell 2011；Asterhan & Schwarz 2016）")
    add_body(doc, "核心：论证是可教的；论证质量可用 TAP（Toulmin Argument Pattern）编码（数据/正当理由/支援/反驳/限定）；"
                  "Asterhan & Schwarz 的 AFL 框架提醒：讨论的“前因（antecedents）→ 对话特征 → 学习结果”三件套中，"
                  "对话特征（dialogue characteristics）是中介变量，也是唯一可直接干预的一环。")
    add_list_para(doc, "→ 对实验：四维 rubric 的 D2（证据与正当理由）直接对应 TAP 的数据+正当理由+支援；"
                       "AFL 框架则是教师模式消融设计的理论骨架：控制同一批题，只改变“对话特征”（无组织 vs 教师引导），"
                       "这正是我们要跑的对照。", 110)

    add_h2(doc, "3.5 B5 协作脚本理论（Fischer 等 2013；Weinberger 等 2010；Stegmann 等 2007）——最强实证证据")
    add_body(doc, "核心：Fischer 等提出脚本理论——外部脚本（教师/系统提供的引导）与参与者内部脚本"
                  "（已有互动模式）相互作用，决定协作质量。实证结论最关键：")
    make_table(
        doc,
        [1.6, 1.5, 1.5],
        ["研究", "设计", "结论"],
        [
            ("Weinberger, Stegmann & Fischer (2010)", "大学生在线论证：无脚本个体 vs 无脚本小组 vs 脚本化小组", "脚本化小组超越个体；无脚本小组并不超越个体"),
            ("Stegmann, Weinberger & Fischer (2007)", "两种协作脚本对论证性知识建构的影响", "脚本显著提升论证质量（构论、反驳、质量）"),
            ("Fischer, Kollar, Stegmann & Wecker (2013)", "脚本理论综述 + 内部/外部脚本互动模型", "引导结构是 CSCL 效果差异的主要来源"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "", after=2)
    add_list_para(doc, "→ 对实验：这是“教师模型”最直接的理论背书——我们的基线（三方无组织互评）"
                       "对应的正是“unscripted group”，而教师模型 = external script。Weinberger 2010 证明："
                       "脚本化是收益来源，不是可有可无的装饰。这也解释了为什么之前“只加提示词”的消融效果不稳——"
                       "提示词若不构成完整的脚本结构（阶段、角色、追问、终止），就还不是 external script。", 110)

    # ---------- 四、两条线合流 ----------
    add_heading(doc, "四、两条线如何在“教师模型”设计里合流：一个推演例子", 1)
    add_body(doc, "以 bad2（SARS-CoV-2 except 题，gold=D，三个模型都理解错指令）为例，"
                  "把 A、B 两条线的部件串成一个教师引导轮次：")
    make_table(
        doc,
        [1.35, 2.6, 1.25],
        ["轮次", "教师动作（引用的理论）", "对应部件"],
        [
            ("第 1 轮", "先不评对错，问 D1 审题：“这道题问的是 except 还是正确表述？”让每个模型复述题目目标（B1 收敛目标 / A1 锚定）", "审题对齐"),
            ("第 2 轮", "追问证据：“你说 C 正确，依据是题干哪个条件？把它和结论之间的命题边写出来”（A2 概念图 / TAP 数据）", "D2 证据"),
            ("第 3 轮", "交叉质询：让模型 B 指出模型 A 推理链的“中间步骤”哪里断了，必须 transact A 的推理（B3）", "transactive 判据"),
            ("第 4 轮", "整合要求：“把三个正确表述连成一张知识网络，标出哪一条是题干限定词约束的”（A3 KIS 整合）", "D4 结构"),
            ("第 5 轮", "收敛检查：各方是否在“论证层面”一致；若只剩答案一致、理由矛盾，继续第 3 轮（B1）", "终止条件"),
        ],
        first_col_bold=True,
    )
    add_body(doc, "要点：这一推演把导师的两个要求（构建联系 + 引导共识）变成了同一套协议的两个维度——"
                  "“联系”是评估对象（A 线），“引导”是过程机制（B 线），二者在每轮教师追问中同时生效。", after=2)

    # ---------- 五、推荐阅读顺序 ----------
    add_heading(doc, "五、推荐阅读顺序", 1)
    add_list_para(doc, "先读 Weinberger 等 (2010)（3 页就能读完的实验报告）——拿到“无引导小组不优于个人”的铁证，"
                       "这是教师模式立项的直接依据。", 110)
    add_list_para(doc, "再读 Fischer 等 (2013) 脚本理论——把“提示词”升级为“脚本”的概念框架。", 110)
    add_list_para(doc, "然后读 Roschelle (1992) 与 Mercer (1996)——定义“什么算达成共识”“什么讨论才有效”。", 110)
    add_list_para(doc, "接着读 Liu 等 (2008) KIS 与 McClure 等 (1999) 概念图评分——把“构建联系”变成可评分的四维 rubric 升级版。", 110)
    add_list_para(doc, "最后读 Gentner (1983) 与 Asterhan & Schwarz (2016)——为 pairwise 比较与教师消融设计找理论基础。", 110)

    # ---------- 参考文献 ----------
    add_heading(doc, "六、新增参考文献（17 篇，出处已核实）", 1)
    for ref in [
        "Ausubel, D. P. (1968). Educational Psychology: A Cognitive View. Holt, Rinehart & Winston.",
        "Novak, J. D., & Gowin, D. B. (1984). Learning How to Learn. Cambridge University Press.",
        "Novak, J. D. (1990). Concept mapping brings long-term movement toward meaningful learning. Science Education, 74(4).",
        "Linn, M. C., & Eylon, B.-S. (2011). Science Learning and Instruction: Taking Advantage of Technology to Promote Knowledge Integration. Routledge.",
        "Liu, O. L., Lee, H.-S., Hofstetter, C., & Linn, M. C. (2008). Assessing knowledge integration in science: Construct, measures, and evidence. Educational Assessment, 13(1), 33–55.",
        "Gentner, D. (1983). Structure-mapping: A theoretical framework for analogy. Cognitive Science, 7(2), 155–170.",
        "Gick, M. L., & Holyoak, K. J. (1983). Schema induction and analogical transfer. Cognitive Psychology, 15(1), 1–38.",
        "McClure, J. R., Sonak, B., & Suen, H. K. (1999). Concept map assessment of classroom learning: Reliability, validity, and logistical practicality. Journal of Research in Science Teaching, 36(4), 475–492.",
        "Roschelle, J. (1992). Learning by collaborating: Convergent conceptual change. Journal of the Learning Sciences, 2(3), 235–276.",
        "Mercer, N. (1996). The quality of talk in children's collaborative activity in the classroom. Learning and Instruction, 6(4), 359–377.",
        "Berkowitz, M. W., & Gibbs, J. C. (1983). Measuring the developmental features of moral discussion. Merrill-Palmer Quarterly, 29(4), 399–410.",
        "Osborne, J., Erduran, S., & Simon, S. (2004). Enhancing the quality of argumentation in school science. Journal of Research in Science Teaching, 41(10), 994–1020.",
        "Kuhn, D., & Crowell, A. (2011). Dialogic argumentation as a vehicle for developing young adolescents' thinking. Psychological Science, 22(4), 545–552.",
        "Asterhan, C. S. C., & Schwarz, B. B. (2016). Argumentation for learning: Well-trodden paths and unexplored territories. Educational Psychologist, 51(2), 164–187.",
        "Fischer, F., Kollar, I., Stegmann, K., & Wecker, C. (2013). Toward a script theory of guidance in computer-supported collaborative learning. Educational Psychologist, 48(1), 56–66.",
        "Weinberger, A., Stegmann, K., & Fischer, F. (2010). Learning to argue online: Scripted groups surpass individuals (unscripted groups do not). Computers in Human Behavior, 26(4), 506–515.",
        "Stegmann, K., Weinberger, A., & Fischer, F. (2007). Facilitating argumentative knowledge construction with computer-supported collaboration scripts. International Journal of Computer-Supported Collaborative Learning, 2(4), 421–447.",
    ]:
        add_ref(doc, ref)

    add_body(doc, "衔接既有清单（已在《教育理论基础文献清单》列出，不再重复）：Vygotsky (1978)；"
                  "Collins, Brown & Newman (1989)；Palincsar & Brown (1984)；van Zee & Minstrell (1997)；"
                  "Paul & Elder (2007)；Graesser & Person (1994)；van Eemeren & Grootendorst (2004)；"
                  "Chi (2009)；Alfieri 等 (2013)；Facione (1990)；Toulmin (1958)；Biggs & Collis (1982)；"
                  "Mislevy 等 (2003)；Brookhart (2013)。", after=4)

    out = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/教育理论深挖_构建联系与引导共识.docx"
    doc.save(out)
    print("saved:", out)


if __name__ == "__main__":
    build()
