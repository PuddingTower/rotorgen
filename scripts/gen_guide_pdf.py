# -*- coding: utf-8 -*-
"""Generate docs/PIPELINE_GUIDE.pdf -- plain-language pipeline guide.

Body via ReportLab + cover via cover_render (PDF skill), merged with pypdf.
Mirrors docs/PIPELINE_GUIDE.md; flowcharts from docs/flow_figs/ (matplotlib).
"""
import sys, os, hashlib

PDF_SKILL_DIR = r"C:\Users\Administrator\.zcode\cli\plugins\cache\zcode-plugins-official\pdf\0.2.2\skills\pdf"
sys.path.insert(0, os.path.join(PDF_SKILL_DIR, "scripts"))

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, PageBreak, CondPageBreak,
                                KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from PIL import Image as PILImage

ACCENT = colors.HexColor('#368aa6')
TEXT_PRIMARY = colors.HexColor('#1c1c1a')
TEXT_MUTED = colors.HexColor('#78766f')
CARD_BG = colors.HexColor('#e8e7e4')
STRIPE = colors.HexColor('#eeedeb')

pdfmetrics.registerFont(TTFont('SimHei', r'C:\Windows\Fonts\simhei.ttf'))
pdfmetrics.registerFont(TTFont('Times New Roman', r'C:\Windows\Fonts\times.ttf'))
pdfmetrics.registerFont(TTFont('CodeFont', r'C:\Windows\Fonts\consola.ttf'))
registerFontFamily('SimHei', normal='SimHei', bold='SimHei')
registerFontFamily('Times New Roman', normal='Times New Roman', bold='Times New Roman')
registerFontFamily('CodeFont', normal='CodeFont', bold='CodeFont')

from pdf import install_font_fallback
install_font_fallback()

OUT_BODY = r"E:\旋翼设计\results\guide_body.pdf"
LM = RM = 2.0 * cm
TM, BM = 2.2 * cm, 2.0 * cm
DOCW = A4[0] - LM - RM

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            self.notify('TOCEntry', (getattr(flowable, 'bookmark_level', 0),
                                     getattr(flowable, 'bookmark_text', ''),
                                     self.page,
                                     getattr(flowable, 'bookmark_key', '')))

S = {}
S['h1'] = ParagraphStyle('H1', fontName='SimHei', fontSize=15, leading=21,
                         textColor=TEXT_PRIMARY, spaceBefore=15, spaceAfter=4,
                         wordWrap='CJK')
S['h2'] = ParagraphStyle('H2', fontName='SimHei', fontSize=12, leading=17,
                         textColor=ACCENT, spaceBefore=12, spaceAfter=4, wordWrap='CJK')
S['body'] = ParagraphStyle('Body', fontName='SimHei', fontSize=10.5, leading=16.5,
                           textColor=TEXT_PRIMARY, alignment=TA_LEFT, wordWrap='CJK',
                           spaceAfter=5, firstLineIndent=21)
S['bodyni'] = ParagraphStyle('BodyNI', parent=S['body'], firstLineIndent=0)
S['caption'] = ParagraphStyle('Cap', fontName='SimHei', fontSize=8.5, leading=12,
                              textColor=TEXT_MUTED, alignment=TA_CENTER, wordWrap='CJK',
                              spaceBefore=3, spaceAfter=6)
S['th'] = ParagraphStyle('TH', fontName='SimHei', fontSize=9, leading=12.5,
                         textColor=colors.white, alignment=TA_CENTER, wordWrap='CJK')
S['td'] = ParagraphStyle('TD', fontName='SimHei', fontSize=8.5, leading=12,
                         textColor=TEXT_PRIMARY, alignment=TA_LEFT, wordWrap='CJK')
S['tdc'] = ParagraphStyle('TDC', parent=S['td'], alignment=TA_CENTER)
S['code'] = ParagraphStyle('Code', fontName='CodeFont', fontSize=9, leading=13.5,
                           textColor=TEXT_PRIMARY, backColor=STRIPE, borderPadding=6,
                           leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=4)
S['toc_t'] = ParagraphStyle('TOCTitle', fontName='SimHei', fontSize=18, leading=26,
                            textColor=TEXT_PRIMARY, spaceAfter=14)
S['stat'] = ParagraphStyle('Stat', fontName='SimHei', fontSize=11, leading=17,
                           textColor=TEXT_PRIMARY, wordWrap='CJK')

def H(text, level=0):
    key = 'h_%s' % hashlib.md5(text.encode()).hexdigest()[:8]
    p = Paragraph('<a name="%s"/><b>%s</b>' % (key, text), S['h1'] if level == 0 else S['h2'])
    p.bookmark_name = text; p.bookmark_level = level
    p.bookmark_text = text; p.bookmark_key = key
    return p

def fig(path, cap, maxh=300):
    im = PILImage.open(path); w, h = im.size
    r = min(DOCW / w, maxh / h, 1.0)
    return [Spacer(1, 4), Image(path, width=w * r, height=h * r),
            Paragraph(cap, S['caption'])]

def tbl(header, rows, ratios, aligns=None):
    widths = [r * DOCW for r in ratios]
    assert abs(sum(widths) - DOCW) < 1.0
    data = [[Paragraph('<b>%s</b>' % c, S['th']) for c in header]]
    for row in rows:
        cells = []
        for j, c in enumerate(row):
            st = S['tdc'] if (aligns and aligns[j] == 'c') else S['td']
            cells.append(Paragraph(str(c), st))
        data.append(cells)
    t = Table(data, colWidths=widths, hAlign='CENTER', repeatRows=1)
    style = [('BACKGROUND', (0, 0), (-1, 0), ACCENT),
             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
             ('GRID', (0, 0), (-1, -1), 0.4, TEXT_MUTED),
             ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
             ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]
    for i in range(1, len(data)):
        style.append(('BACKGROUND', (0, i), (-1, i),
                      colors.white if i % 2 == 1 else STRIPE))
    t.setStyle(TableStyle(style))
    return t

def callout(text):
    tb = Table([[Paragraph(text, S['stat'])]], colWidths=[DOCW * 0.96])
    tb.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('LINEBEFORE', (0, 0), (0, -1), 3, ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    tb.hAlign = 'CENTER'
    return tb

def on_page(canv, doc):
    canv.saveState()
    canv.setFont('SimHei', 7.5); canv.setFillColor(TEXT_MUTED)
    canv.drawString(LM, A4[1] - 1.35 * cm, '悬停旋翼设计管线 · 全流程图解（人话版）')
    canv.setStrokeColor(ACCENT); canv.setLineWidth(1.2)
    canv.line(LM, A4[1] - 1.55 * cm, A4[0] - RM, A4[1] - 1.55 * cm)
    canv.setFont('SimHei', 7.5)
    canv.drawString(LM, 1.2 * cm, 'rotorgen · 2026-10-25')
    canv.drawRightString(A4[0] - RM, 1.2 * cm, '第 %d 页' % doc.page)
    canv.restoreState()

doc = TocDocTemplate(OUT_BODY, pagesize=A4, leftMargin=LM, rightMargin=RM,
                     topMargin=TM, bottomMargin=BM,
                     title='rotorgen 全流程图解（人话版）',
                     author='Z.ai GLM', creator='Z.ai',
                     subject='悬停旋翼设计管线全流程：模块逻辑与算法（人话版）')

story = []
FF = r"E:\旋翼设计\docs\flow_figs"

story.append(Paragraph('<b>目录</b>', S['toc_t']))
toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle('TOC1', fontName='SimHei', fontSize=11, leading=18, leftIndent=16,
                   textColor=TEXT_PRIMARY),
]
story.append(toc)
story.append(PageBreak())

# ---------------------------------------------------------------- 0 what is this
story.append(H('一、这个项目到底是干嘛的（30 秒版本）', 0))
story.append(Paragraph(
    '想象有人给你提了一个要求："帮我设计一台直径 2.08 米的\'电风扇\'，要能往上吹出 200 公斤的力，'
    '只用 2 片叶子，叶子后缘厚度必须是 2 毫米，而且悬停时要尽量省电。"', S['bodyni']))
story.append(Paragraph(
    '这个程序接单后<b>全自动</b>做完五件事：①自己画出叶片每个截面的翼型形状（机翼剖面）；'
    '②自己决定叶片的平面形状（哪里宽哪里窄）和扭转角（叶根到叶尖各拧多少度）；'
    '③用自研气动求解器算出"这么设计要耗多少电"；④反复微调形状，一代一代试，直到电耗降不下去；'
    '⑤输出一整套图纸和性能报告。', S['bodyni']))
story.append(Spacer(1, 4))
story.append(callout(
    '<b>输入是 4 个数字，输出是一套可制造的图纸。</b>全程不需要任何商业软件（无 CAE/CFD 许可证），'
    '只依赖 numpy / scipy / numba / matplotlib 和一台普通电脑，完整寻优一晚上跑完。'))

# ---------------------------------------------------------------- 1 main flow
story.append(H('二、全流程总图', 0))
story.append(Paragraph(
    '从 4 个输入数字到交付图纸的完整链路。核心循环是：优化器出一组"基因"（设计向量）→ '
    '翻译成桨叶形状 → 算出耗电 → 优化器总结经验出下一组。防假货机制（每 8 代高保真抽查）'
    '在右路把关。', S['bodyni']))
story.extend(fig(os.path.join(FF, 'fig_flow_main.png'),
                 '图 1：端到端主流程（含优化循环与防假货抽查）', maxh=620))

story.append(PageBreak())
story.append(H('三、3D 求解器的内循环', 0))
story.append(Paragraph(
    '3D 求解器是一个"鸡生蛋"问题：环量决定尾迹，尾迹诱导风速，风速决定迎角，迎角又决定环量。'
    '解法是不动点迭代 + 松弛：先猜一份环量，循环"算诱导风→查表得升阻→反推新环量"，'
    '直到前后两次环量几乎不再变化。', S['bodyni']))
story.extend(fig(os.path.join(FF, 'fig_flow_wake.png'),
                 '图 2：自由尾迹内循环（尾迹形状不预设，自由漂移收敛）', maxh=500))

# ---------------------------------------------------------------- 2 glossary
story.append(H('四、名词小词典（浓缩版）', 0))
story.append(Paragraph('完整版见 docs/PIPELINE_GUIDE.md 第 2 节。', S['caption']))
story.append(Paragraph('4.1 旋翼零件与性能指标', S['h2']))
story.append(tbl(['名词', '人话解释'],
                 [['弦长 c / t/c / 弯度', '翼型截面的宽度 / 最厚处除以弦长 / 中弧线弓起的高度（弓得越狠升力越大阻力也大）'],
                  ['扭转 / 总距', '叶片从根到尖逐渐"拧"的角度（叶尖转得快需要迎角小）/ 整片桨一起拧的基准角（直升机的油门）'],
                  ['实度 σ', '所有叶片面积 ÷ 桨盘面积，"叶子盖住圆面的比例"'],
                  ['CT / CQ / FM', '推力、扭矩的无量纲系数（让大小不同的桨可比）/ 悬停品质因数 = 理想最小功率 ÷ 实际功率，'
                   '即"离物理满分有多近"，本项目唯一目标'],
                  ['配平', '拧总距直到拉力正好 = 200 kgf']],
                 [0.22, 0.78]))
story.append(Paragraph('4.2 项目自造的词', S['h2']))
story.append(tbl(['名词', '人话解释'],
                 [['三档尾迹', '尾迹追多细追多远的三个固定档位：fast≈13s/次（优化内环）、hi-fi≈25s/次（抽查）、'
                   'ultra≈57s/次（终验）——像看烟圈：帧率越高跟得越久越真实，也越费时间'],
                  ['φ=1.2（入流修正）', '尾迹切成格子算会导致桨叶处下洗风系统性低估，对实验扫描后乘 1.2 修正。管推力读数'],
                  ['κ_cal=1.2（功率定标）', '所有算例扭矩被系统性低估 15~25%，诱导功率整体乘 1.2 让读数贴近实验。管功率读数'],
                  ['κ_B（已删）', 'κ_cal 的前任"毯子因子"，无条件 ×1.2，实为重复惩罚，已删除'],
                  ['Cd×1.15 硬修正', '自研 2D 阻力比实验低 12~18%，表格里直接乘 1.15 防优化器追假低阻'],
                  ['瓦特账本', '功率拆成 P_axial（压空气下行的功）+ P_swirl（尾流打转动能）+ P_prof（表面摩擦），'
                   '每瓦有去向、无隐藏系数'],
                  ['幻影最优', '粗档里找到的"超级好设计"，细档复核就露馅（通常把失速藏在粗模型看不见的地方）'],
                  ['Gate A/B/C', '自定的三道验收关卡（模型准/够快/达标），每道预先写好止损条款']],
                 [0.24, 0.76]))
story.append(Paragraph('4.3 求解器黑话', S['h2']))
story.append(tbl(['名词', '人话解释'],
                 [['BEMT（被禁）', '教科书标配的"叶素-动量理论"，快但算不准桨尖涡与尾迹收缩。本项目红线：禁止当求解器'],
                  ['自由尾迹', '不预设尾迹形状，让每段涡按当地风速自由漂移，自己收敛成真实的收缩螺旋'],
                  ['Biot–Savart / 涡核', '"一根通了风的导线在旁边吹多大风"的物理定律 / 给涡一个软芯半径，避免中心速度爆炸'],
                  ['桨尖涡 / 环量 Γ', '叶尖甩出的最强漩涡（悬停直升机下洗的烟圈）/ 每段桨叶"背着"的升力强度，升力 = ρ·V·Γ'],
                  ['PIPC', '尾迹节点漂移的数值格式（预测-校正+超松弛），悬停自由尾迹经典算法（Bagai–Leishman 1995）'],
                  ['面板法 / 边界层', '把翼型表面切成小段贴涡解方程（升力）/ 贴壁薄空气层的摩擦与分离（阻力与失速）'],
                  ['CST 参数化', '用一组可调系数描述任意翼型形状的数学语言，"翼型的基因"'],
                  ['CMA-ES / Nelder–Mead', '一群候选每代撒出去试、表现好的方向拉大撒网椭圆的进化优化器 / '
                   '"一个盲人拿三角形下山"的简单寻优法（7 维时代老将）']],
                 [0.24, 0.76]))

# ---------------------------------------------------------------- 3 modules
story.append(H('五、模块说明书', 0))
mods = [
    ('airfoil.py — 翼型几何工具箱（304 行）',
     '定义"翼型是什么"（一圈封闭坐标点，钝尾缘=首尾两点留 2mm 开口），提供 NACA 教科书生成器、'
     'CST 参数化生成器、余弦重采样（前尾缘自动加密）、旋转平移、读写 .dat、算最大厚度/弯度/前缘半径。'
     '上层模块只需要"一圈坐标点"这一种表达。'),
    ('famgen.py — 翼型一家人生成器（65 行）',
     '沿展向长出一族互相衔接的翼型：站位 r → 厚度按 tc(r)=tc_root+(tc_tip−tc_root)·r^1.2 插值；'
     '当地弦长 c（米）→ 尾缘相对开口 = 0.002÷c 注入 CST 尾缘项。所以无论弦长多少，'
     '尾缘开口永远是 2 毫米——硬约束逐站位精确执行（12 站位实测全过，见验证报告）。'
     '已知瑕疵：弯度标定偏 27%，待重标定。'),
    ('panel2d.py — 2D 无粘面板法（398 行，mini-XFOIL 的心脏）',
     '把翼型表面切成 ~160 个小段（面板），每段贴一条强度线性变化的旋涡；"空气不能穿进表面"给出方程组，'
     '尾缘补 Kutta 条件（上下表面到尾缘速度相等）定出唯一解。三个诀窍：矩阵只和几何有关，分解一次后每个'
     '迎角 O(N) 秒解；预解 0° 和 90° 两个"单位来流"，任意迎角线性组合；钝尾缘补源+涡组合面板消角点奇性。'
     '可压缩性用 Kármán–Tsien 修正。'),
    ('bl2d.py — 边界层积分法（192 行）',
     '算摩擦阻力和分离（失速）。三段接力：Thwaites 层流段从驻点一步步积分动量厚度 → Michel 判据'
     '（何时层流撑不住变湍流）→ Head 湍流段（"卷吸方程"，边界层像滚雪球把外流卷进来）推进到尾缘。'
     '阻力 = Squire–Young 在尾缘收割动量损失 + Hoerner 钝尾缘底阻。历史坑（已解决）：湍流方程刚转捩时'
     '数值爆炸→改守恒形式；前缘分离泡误判失速→泡后重置形状因子。'),
    ('foil2d.py — 2D 总装车间（136 行）',
     '输入一个翼型，输出整条极线（一串迎角的 Cl/Cd/Cm）。流水线：面板法解无粘 → 沿表面从驻点"行军"'
     '算边界层 → 边界层的排挤效应换算成小"吹气"速度重解一次面板法（粘性-无粘耦合）→ '
     '升力=环量×ρV，阻力=摩擦+底阻 → 分离则升力打折并标记失速。约 3 ms/迎角。'),
    ('kernels3d.py — 涡的数学发动机（76 行）',
     '一段直线涡在任意点激起的风速：精确有限段 Biot–Savart 公式加涡核正则化（涡核→0 时严格退化回'
     '教科书解；核有限时中心速度有界）。Numba JIT 多核并行，每秒几十亿"段×点"对——'
     '这是"自由尾迹能塞进优化环"的物理前提。'),
    ('rotor3d.py — 3D 自由尾迹求解器（439 行，重头戏）',
     '桨叶用环量分布 Γ(r) 描述；环量被叶尖叶根"甩"出去，沿尾缘拖出螺旋状涡面，叶尖那圈最强=桨尖涡。'
     '尾迹不预设形状：每个涡节点按当地合速度自由漂移（PIPC 预测-校正+松弛 1.3+步长限幅），'
     '近处 3.5~9 圈自由演化、更远处冻结、最外圈解析螺线延长。主循环"载荷↔环量"不动点迭代 22~34 次，'
     '松弛 0.35 防振荡，环量变化 <3e-4 收敛。三个工程稳定器（防数值毛刺非物理假设）：诱导速度限幅、'
     '展向三点平滑、弦向 3 条采样线平均。输出推力/功率/瓦特账本/无量纲系数。'),
    ('design_opt.py / design_opt2.py — "基因"翻译官（194/261 行）',
     '17 维设计向量 = 桨尖速度 + 扭角 6 控制点单调样条 + 弦长 5 控制 PCHIP + 弯度 3 点 + 根/尖厚度。'
     '配平：总距 8°→18° 粗扫后割线细调到拉力误差 <2~3%（每个候选要完整重跑 2~4 次 3D 求解，耗时大头）。'
     '约束（违反罚 1e6）：桨尖马赫 ≤0.52、根部厚度 ≥12%、升力 ≤0.85×Cl_max。'
     '极线缓存按（截面,Re,M）为键，命中率 86%——同族翼型反复出现时 2D 计算几乎免费。'),
    ('opt_cmaes.py — CMA-ES 优化器（194 行）',
     '每代撒 14 个"探险者"试不同基因组合，表现好的方向把下一代的"撒网椭圆"（均值+协方差）挪过去、拉过来，'
     '自动放大缩小探索范围。多保真调度：内环全用 fast 档（~30-45 秒/候选含配平），每 8 代把当前最优拉到 '
     'hi-fi 档重考——fast 档成绩作数与否以 hi-fi 为准。每个候选完整记录到 JSONL 可续跑；'
     '独立监工每 30 分钟巡检、崩溃自动重启、连崩 3 次熔断。'),
    ('finalize.py — 交付车间（134 行）',
     '最终高保真复核 + 输出图纸：41 站位几何 CSV、12 个站位翼型 .dat（真实弦长、文件名含 2mm 标识）、'
     '三维叶面点云（可进 CAD）、performance.json 全性能明细。'),
    ('bench2.py / run_bench.py — 考试系统',
     '硬编码 Caradonna–Tung（悬停基准之王，与设计同规格）、Martin–Tung、Harrington、DJI 9450 的几何与'
     '实验数据，自动跑分输出误差矩阵。数据源 CSV 与配套基准仓库逐位核对一致。'),
    ('verify_light / heavy / figs.py — 审计团队',
     '第三方审计自动化后盾：light（秒级）涡核公式 vs 解析解、FM 恒等式、数据源逐位核对、κ 扫描；'
     'heavy（~4 分钟）复跑基准核心工况与交付叶片对答案；figs 重画验证报告全部 11 张图。'),
]
for title, txt in mods:
    story.append(CondPageBreak(3.0 * cm))
    story.append(H(title, 1))
    story.append(Paragraph(txt, S['body']))

# ---------------------------------------------------------------- 4 journey
story.append(H('六、一次评估的完整旅程（时间去哪了）', 0))
story.append(tbl(['步骤', '干什么', '耗时'],
                 [['1', '边界检查：设计向量出界直接判 100 万分出局', '~0'],
                  ['2', '翻译：17 个数 → 扭角/弦长/弯度曲线 → 18 个站位翼型', '毫秒级'],
                  ['3', '每站位 2D 极线（52 迎角）：缓存命中则 0，未命中 ~0.2 秒/站位', '0~2 秒'],
                  ['4', '配平第 1 次求解：3D 自由尾迹 fast 档（22 轮外迭代）', '~13 秒'],
                  ['5', '配平第 2~4 次求解（割线逼近 200 kgf）', '~13-40 秒'],
                  ['6', '约束检查（失速/马赫/厚度）', '毫秒级'],
                  ['7', '记录到 JSONL，新最优则更新 best 文件', '毫秒级']],
                 [0.08, 0.72, 0.20], aligns=['c', 'l', 'c']))
story.append(Paragraph(
    '表 5：单候选评估流水线（fast 档实测 ~30-45 秒；一次完整寻优 = 40 代 × 14 候选 ≈ 一夜）', S['caption']))

story.append(H('七、三档尾迹：快慢之间的取舍', 0))
story.append(tbl(['档位', '每步转角 dψ', '追几圈', '单次求解', '用在哪'],
                 [['fast（快档）', '10°', '4.5 圈', '~13 秒', '优化内环，跑几千次的那种'],
                  ['hi-fi（高保真档）', '7.5°', '6 圈', '~25 秒', '每 8 代抽查优化结果'],
                  ['ultra（超深档）', '5°', '10 圈', '~57 秒', '最终交付前算总账']],
                 [0.22, 0.18, 0.14, 0.16, 0.30], aligns=['l', 'c', 'c', 'c', 'l']))
story.append(Paragraph('表 6：尾迹分辨率三档', S['caption']))

# ---------------------------------------------------------------- 5 red line
story.append(H('八、红线自证：为什么敢说"没用 BEMT"', 0))
story.append(Paragraph(
    '红线原文：禁止用 BEMT（叶素-动量理论）及其一维动量变体作为求解器。本项目的实现：'
    '①每一个点的诱导风都来自"尾迹上所有涡段 + 所有桨叶附着涡"的 Biot–Savart 直接求和——'
    '没有任何一步用动量公式求入流；②尾迹收缩、下沉、桨-涡干扰、叶尖损失全部是自由尾迹解出来的结果，'
    '且与实验对账通过（桨尖涡转 180° 后半径 0.897R vs 实验 0.905R，差 0.9%）；'
    '③动量理论唯一出场的地方是 FM 的分母（理想功率下限）——那是拿教科书公式当"满分线"来打分，'
    '不参与任何流场求解。', S['bodyni']))

# ---------------------------------------------------------------- 6 files
story.append(H('九、文件地图与快速上手', 0))
story.append(Paragraph(
    'src/rotorgen/：airfoil.py famgen.py（翼型几何+族）· panel2d.py bl2d.py foil2d.py（2D 链）· '
    'kernels3d.py rotor3d.py（3D 链）<br/>scripts/：design_opt.py design_opt2.py（参数化+配平）· '
    'opt_cmaes.py（寻优）· finalize.py（交付）· bench2.py run_bench.py（基准）· '
    'verify_light.py verify_heavy.py verify_figs.py（审计）<br/>results/：基准成绩、优化轨迹、交付物　'
    'docs/：本文档、验证报告、FM075 计划', S['bodyni']))
story.append(Paragraph('pip install -r requirements.txt        <font name="SimHei"># Python 3.12+；仅 numpy/scipy/numba/matplotlib/cma</font>', S['code']))
story.append(Paragraph('python scripts/run_bench.py             <font name="SimHei"># 跑基准考试（对答案）</font>', S['code']))
story.append(Paragraph('python scripts/design_opt2.py           <font name="SimHei"># 冒烟：评估种子设计一次</font>', S['code']))
story.append(Paragraph('python scripts/opt_cmaes.py             <font name="SimHei"># 端到端寻优（约一夜）</font>', S['code']))
story.append(Paragraph('python scripts/verify_light.py          <font name="SimHei"># 秒级自检</font>', S['code']))
story.append(Spacer(1, 8))
story.append(Paragraph(
    '想深入某个专题：所有失败与修复的完整记录 → RESEARCH_AND_BENCHMARK_LOG.md；每个数字准不准、'
    '哪些坑还没填 → VERIFICATION_REPORT.pdf（人话版）；FM 0.75 目标的路线图 → docs/FM075_PLAN.md。',
    S['bodyni']))

doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
print('body ->', OUT_BODY)

# ---------------------------------------------------------------- cover + merge
from cover_render import render_cover, detect_fonts
from pypdf import PdfReader, PdfWriter, Transformation

content = {
    "kicker": "全流程图解 · PIPELINE GUIDE",
    "hero": "悬停旋翼设计管线",
    "summary": "从 4 个输入数字到一整套可制造图纸：翼型族 → 2D 升阻表 → 3D 自由尾迹 → 配平 → "
               "CMA-ES 寻优的全链路流程图与模块说明书。每个模块的逻辑与算法用人话讲清，"
               "所有行话第一次出现都当场解释。",
    "meta": "2026-10-25 · 配套《验证报告（人话版）》",
    "footer": "ROTORGEN PIPELINE GUIDE · DOC 2026-GUIDE-001",
    "year": "2026", "word": "FLOW",
}
palette = {"primary": "#368aa6", "text": "#1c1c1a", "muted": "#78766f", "bg": "#ffffff"}
fonts = detect_fonts()
render_cover("03", content, r"E:\旋翼设计\results\guide_cover.pdf",
             palette=palette, fonts=fonts)

A4_W, A4_H = 595.28, 841.89
def norm(page):
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    if abs(w - A4_W) > 2 or abs(h - A4_H) > 2:
        page.add_transformation(Transformation().scale(A4_W / w, A4_H / h))
        page.mediabox.lower_left = (0, 0); page.mediabox.upper_right = (A4_W, A4_H)
    return page

w = PdfWriter()
w.add_page(norm(PdfReader(r"E:\旋翼设计\results\guide_cover.pdf").pages[0]))
for p in PdfReader(OUT_BODY).pages:
    w.add_page(norm(p))
w.add_metadata({'/Title': 'rotorgen 全流程图解（人话版）', '/Author': 'Z.ai GLM',
                '/Creator': 'Z.ai', '/Subject': '悬停旋翼设计管线模块逻辑与算法（人话版）'})
out = r"E:\旋翼设计\docs\PIPELINE_GUIDE.pdf"
with open(out, 'wb') as f:
    w.write(f)
print('final ->', out)
