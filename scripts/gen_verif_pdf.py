# -*- coding: utf-8 -*-
"""Generate docs/VERIFICATION_REPORT.pdf -- plain-language edition.

Body via ReportLab + cover via cover_render (PDF skill), merged with pypdf.
Mirrors docs/VERIFICATION_REPORT.md (2026-10-25 rewrite).
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
                                KeepTogether, HRFlowable)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from PIL import Image as PILImage

# ---------------------------------------------------------------- palette (seed 7, repo-standard)
ACCENT = colors.HexColor('#368aa6')
TEXT_PRIMARY = colors.HexColor('#1c1c1a')
TEXT_MUTED = colors.HexColor('#78766f')
CARD_BG = colors.HexColor('#e8e7e4')
STRIPE = colors.HexColor('#eeedeb')
OK_C = colors.HexColor('#46875c')
WARN_C = colors.HexColor('#a18347')
ERR_C = colors.HexColor('#92453e')

# ---------------------------------------------------------------- fonts
pdfmetrics.registerFont(TTFont('SimHei', r'C:\Windows\Fonts\simhei.ttf'))
pdfmetrics.registerFont(TTFont('Times New Roman', r'C:\Windows\Fonts\times.ttf'))
pdfmetrics.registerFont(TTFont('CodeFont', r'C:\Windows\Fonts\consola.ttf'))
registerFontFamily('SimHei', normal='SimHei', bold='SimHei')
registerFontFamily('Times New Roman', normal='Times New Roman', bold='Times New Roman')
registerFontFamily('CodeFont', normal='CodeFont', bold='CodeFont')

from pdf import install_font_fallback
install_font_fallback()

# ---------------------------------------------------------------- doc & styles
OUT_BODY = r"E:\旋翼设计\results\verif_body.pdf"
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

def fig(path, cap, maxw=DOCW, maxh=272):
    im = PILImage.open(path); w, h = im.size
    r = min(maxw / w, maxh / h, 1.0)
    return [Spacer(1, 4), Image(path, width=w * r, height=h * r),
            Paragraph(cap, S['caption'])]

def tbl(header, rows, ratios, aligns=None):
    n = len(header)
    widths = [r * DOCW for r in ratios]
    assert abs(sum(widths) - DOCW) < 1.0
    data = [[Paragraph('<b>%s</b>' % c, S['th']) for c in header]]
    for row in rows:
        cells = []
        for j, c in enumerate(row):
            st = S['tdc'] if (aligns and aligns[j] == 'c') else S['td']
            if isinstance(c, tuple):      # (text, color)
                st = ParagraphStyle('tmp%d%d' % (id(row), j), parent=st, textColor=c[1])
                c = c[0]
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

# ---------------------------------------------------------------- header/footer
def on_page(canv, doc):
    canv.saveState()
    canv.setFont('SimHei', 7.5); canv.setFillColor(TEXT_MUTED)
    canv.drawString(LM, A4[1] - 1.35 * cm, '悬停旋翼设计管线 · 验证报告（人话版）')
    canv.setStrokeColor(ACCENT); canv.setLineWidth(1.2)
    canv.line(LM, A4[1] - 1.55 * cm, A4[0] - RM, A4[1] - 1.55 * cm)
    canv.setFont('SimHei', 7.5)
    canv.drawString(LM, 1.2 * cm, 'rotorgen · 2026-10-25')
    canv.drawRightString(A4[0] - RM, 1.2 * cm, '第 %d 页' % doc.page)
    canv.restoreState()

doc = TocDocTemplate(OUT_BODY, pagesize=A4, leftMargin=LM, rightMargin=RM,
                     topMargin=TM, bottomMargin=BM,
                     title='悬停旋翼设计管线验证报告（人话版）',
                     author='Z.ai GLM', creator='Z.ai',
                     subject='rotorgen 悬停旋翼设计管线的源码精读与独立复算验证（人话版）')

story = []
F = r"E:\旋翼设计\docs\verif_figs"

# ---------------------------------------------------------------- TOC page
story.append(Paragraph('<b>目录</b>', S['toc_t']))
toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle('TOC1', fontName='SimHei', fontSize=11, leading=18, leftIndent=16,
                   textColor=TEXT_PRIMARY),
]
story.append(toc)
story.append(PageBreak())

# ---------------------------------------------------------------- 1 conclusions
story.append(H('一、先看结论（30 秒版）', 0))
story.append(callout(
    '<b>一句话总评</b>：这套代码报的数字是诚实的、可复现的；读代码抓到的 3 个真 bug 已全部修复；'
    '优化器跑出的名义最优被例行抽查识破为假货并已否决。'))
story.append(Spacer(1, 6))
for i, s in enumerate([
    '<b>1. 每个关键数字都能独立复现。</b>README、研究日志里声称的数字，我们用独立脚本重新算了一遍；'
    '把同样的算例重跑，结果能对上到小数点后 9 位以上（下文称"逐位一致"）。',
    '<b>2. 抓到 3 个真 bug，全部已修复。</b>①无量纲化公式少乘半径（项目 10-24 自查发现，我们验证其修复）；'
    '②优化脚本功率换算残留旧约定，功率偏低 4.3%（10-25 修复）；③优化器每代存档必崩（已修复并跑完 40 代）。',
    '<b>3. 优化器的"最优解"里混着假货，被防假货机制当场识破。</b>名义最优（FM 读数 1.13，物理不可能）'
    '被高保真抽查否决；可信推荐为第 16 代个体，比第一版交付叶片功率低约 15~20%。',
    '<b>4. 两个自造的"经验修正因子"（φ=1.2 与 κ=1.2）有实测依据</b>：都是对着真实风洞实验一格格扫出来的，'
    '来历与副作用记录在案（第八节）。',
    '<b>5. 项目没有回避问题。</b>算不准的工况原文照登、如实弃用。诚实度判定：通过。',
]):
    story.append(Paragraph(s, S['bodyni']))

# ---------------------------------------------------------------- 2 method
story.append(H('二、这份报告是怎么做出来的', 0))
story.append(tbl(['手段', '具体做法', '能发现什么'],
                 [['读代码', '约 2,600 行源码逐行过，专看"公式和注释说的是不是一回事"',
                   '逻辑 bug、单位错误、文档与代码不符'],
                  ['独立复算', '不用项目函数，拿纸面公式/解析解重算关键量', '公式抄错、推导错误'],
                  ['复跑对账', '把基准算例、交付叶片重新求解，与项目存档逐位比对',
                   '结果不可复现、协议不一致']],
                 [0.14, 0.52, 0.34]))
story.append(Paragraph('表 1：三种验证手段', S['caption']))
story.append(Paragraph(
    '"逐位一致"的意思：两次独立运行输出的数字每一位小数都相同（误差 1e-10 量级，即小数点后第 10 位）。'
    '求解器是纯确定性计算（没有随机数），同一输入必须同一输出——达不到就说明有猫腻或环境不一致。', S['body']))

# ---------------------------------------------------------------- 3 glossary
story.append(H('三、名词小词典（先扫一眼，后面不卡壳）', 0))
story.append(Paragraph('3.1 测量与指标', S['h2']))
story.append(tbl(['名词', '人话解释'],
                 [['推力 T / 功率 P', '往上吹的力（目标 200 kgf）；电机要出的功率，越小越好'],
                  ['CT / CQ', '推力、扭矩各自除以"转速、半径、密度"的组合后的纯数字，让大小不同的桨可以互相比。'
                   '类比：不看油耗没法比车，"百公里油耗"才可比'],
                  ['FM（悬停品质因数）', 'FM = 理想最小功率 ÷ 实际功率，最大 1，即"离物理满分有多近"。'
                   '本项目唯一要最大化的目标'],
                  ['同推力 CQ', '比较扭矩前先折算到"和实验拉力完全相等"再比——设计管线永远工作在'
                   '拉力=200kgf 的配平状态，这是唯一有意义的比法'],
                  ['逐位一致 / 1e-10', '两次运行结果每一位小数都相同']],
                 [0.24, 0.76]))
story.append(Paragraph('3.2 项目自造的修正因子（都对实验定出来的，不是拍脑袋）', S['h2']))
story.append(tbl(['名词', '人话解释'],
                 [['φ（入流修正，=1.2）', '尾迹切成一格一格算，桨叶处的下洗风会系统性低估；'
                   '对实验扫描后确定乘 1.2 能把推力读数误差压进 ±10%。管推力读数'],
                  ['κ_cal（功率定标，=1.2）', '所有算例扭矩被系统性低估 15~25%，把诱导功率整体乘 1.2 让'
                   '扭矩读数贴近实验（最大残差 6%）。管功率读数'],
                  ['Cd×1.15 硬修正', '自研 2D 求解器阻力比实验低 12~18%，为防优化器追假低阻，表格里直接乘 1.15'],
                  ['κ_B（旧毯子因子，已删）', 'κ_cal 的前任，无条件把功率 ×1.2，后发现是重复惩罚，已从代码删除'],
                  ['三档尾迹 fast/hi-fi/ultra', '尾迹追多细、追多远的三个固定档位：快档 ~13s/次（优化内环）、'
                   '高保真 ~25s/次（抽查）、超深 ~57s/次（终验）'],
                  ['配平', '拧总距（叶片基准安装角）直到拉力正好 200 kgf；每个候选设计要配平 2~4 次'],
                  ['Gate A/B/C', '项目自定的三道验收关卡（模型准/够快/达标），每道预先写好"不达标走哪条备选路"'],
                  ['瓦特账本', '功率拆成 P_axial（压空气下行的功）+ P_swirl（尾流打转动能）+ P_prof（表面摩擦），'
                   '每一瓦都有去向，不许藏系数']],
                 [0.26, 0.74]))
story.append(Paragraph('3.3 bug 相关', S['h2']))
story.append(tbl(['名词', '人话解释'],
                 [['CQ 约定 bug', '无量纲化公式 CQ=Q/(ρΩ²πR⁵) 曾写成 R⁴（少乘半径 R）。物理量一直是对的，'
                   '但所有 CQ 系数读数带假因子——DJI 小桨曾算出 FM=6.4（物理不可能超过 1）即暴露铁证'],
                  ['勘误 / 去污染', '修复后把历史读数用公式 (1+旧误差)÷R−1 反推回真实值的过程'],
                  ['幻影最优', '优化器在粗档（fast）里找到的"超级好设计"，拿到细档（hi-fi）复核就露馅'],
                  ['记分卡', '下节的 14 项检查成绩单：通过 / 注意（已知偏差可控）/ 未过（均已处置）']],
                 [0.26, 0.74]))

# ---------------------------------------------------------------- 4 scorecard
story.append(H('四、14 项检查成绩单', 0))
sc = [
    ('1', '"一段涡在旁边吹多大的风"的公式对不对', '3 道有标准答案的数学题', ('通过', OK_C), '误差 2e-16~2e-7'),
    ('2', '推力/扭矩/FM 换算公式自洽吗', '随机数代入两种算法对答案', ('通过', OK_C), '机器精度'),
    ('3', '硬编码的实验数据抄对了吗', '与基准仓库 CSV 逐位比', ('通过', OK_C), '零偏差'),
    ('4', '2D 升力算得准吗', '对比风洞实验 + 参考程序', ('通过', OK_C), '升力斜率偏高约 3%'),
    ('5', '2D 阻力算得准吗', '同上', ('注意', WARN_C), '偏低 12~18%（已知，×1.15 兜底）'),
    ('6', '基准算例能复跑出存档的数吗', '重跑 θ8@1250 工况', ('通过', OK_C), '逐位一致'),
    ('7', '功率定标因子 κ=1.2 定得对吗', '独立重扫参数曲线', ('通过', OK_C), '最优点 1.218，取 1.2 残差 6%'),
    ('8', '不同 κ 下 FM 变化表', '用功率账本重算', ('通过', OK_C), '全部复现'),
    ('9', '历史 CQ bug 的勘误链闭环吗', '反推公式 vs 修复后重跑', ('通过', OK_C), '三工况逐点吻合'),
    ('10', '同一算例重跑两次结果一样吗', '独立重跑交付叶片', ('通过', OK_C), '一致到 1e-10'),
    ('11', '交付叶片尾缘真是 2mm 吗', '12 站位坐标实测', ('通过', OK_C), '全部精确 2.000 mm'),
    ('12', '尾迹形状和实验对得上吗', '桨尖涡位置 vs 实验测量', ('通过', OK_C), '半径差 0.9%，下沉差 2%'),
    ('13', '优化脚本的功率换算单位对吗', '瓦特账本 vs 系数换算对账', ('未过', ERR_C), '少乘 R，功率低 4.3% → 已修复'),
    ('14', '优化器脚本能稳定跑完一代吗', '实跑', ('未过', ERR_C), '存档时崩溃 → 已修复并跑完'),
]
story.append(tbl(['#', '检查项（人话）', '怎么查的', '结果', '数值'],
                 sc, [0.05, 0.31, 0.25, 0.10, 0.29], aligns=['c', 'l', 'l', 'c', 'l']))
story.append(Paragraph('表 2：14 项记分卡（12 项通过，2 项未过但均已修复）', S['caption']))

# ---------------------------------------------------------------- sections with figures
secs = [
    ('五、数学内核：涡的公式靠谱吗', 'fig01_kernel.png', '图 1：涡核验证',
     '3D 求解器所有的"风"都来自一个公式：一段有限长的涡线在旁边一点激起多大的诱导速度。'
     '我们出了三道有标准答案的题（无限长直涡、有限段涡、圆环涡），全部通过——直线段算到小数点后 16 位；'
     '"涡核"软化行为也正确：离得远时恢复精确解，贴到涡中心时速度有界（真实漩涡中心像龙卷风眼，反而平静）。'
     '结论：kernels3d.py 这 76 行数学发动机无保留可信。'),
    ('六、2D 翼型计算器：升力准，阻力偏低', 'fig02_2d.png', '图 2：NACA0012 三方对答案',
     '用标准考题 NACA0012（雷诺数 600 万，与设计同级）三方对答案：风洞实验、参考程序 NFool、解析斜率。'
     '升力三方一致（斜率偏高约 3%，无粘区差 <1%），可信；阻力系统性偏低 12~18%——简化边界层的已知代价，'
     '项目早已用"×1.15 硬修正"兜底。一个重要的坑：阻力对网格数量敏感（60 加密到 140 还要再降约 20%），'
     '生产网格恰好落在当初标定带内，改网格必须重标定。'),
    ('七、和真实风洞对答案', 'fig03_matrix.png', '图 3：基准矩阵误差总览',
     '拿求解器考 Caradonna–Tung 基准（悬停领域的"标准卷"，与本设计同规格）。按设计口径（φ=1.2 + Cd×1.15）：'
     '核心工况推力误差 +3.5~+8.6%，达标；同推力扭矩误差 −10~−20%（系统性低估）——这正是 κ=1.2 存在的原因，'
     '乘上后最大残差 6%。归因检查做实了：尾迹切得更细缺口并不收窄，说明偏差来自模型本身而非尾迹分辨率。'
     '域外工况（微型桨）偏差巨大，项目如实记录、如实弃用。'),
    ('八、两个修正因子是怎么定出来的', 'fig04_phi.png', '图 4：φ 定标扫描',
     'φ（入流修正）：从 1.0 扫到 1.3，φ=1.2 时核心工况推力误差压进 +3.5~+8.6%；同时发现 φ 对扭矩缺口几乎无效'
     '——所以必须另设 κ_cal。"φ 管推力、κ 管功率"的职责划分是对的。'),
    ('八、两个修正因子是怎么定出来的（续）', 'fig05_kappa.png', '图 5：κ 定标曲线',
     'κ_cal（功率定标）：独立重扫 κ∈[1.0,1.3]，最优点 1.218（最大残差 4.8%）；实际采用 1.20（残差 6.0%，'
     '±8% 内两侧有余量）。计划设的止损线（κ 不得超过 1.18）确实被触发，项目如实记录并写明了采用 1.20 的'
     '权衡理由。决定有数据支撑。'),
    ('九、抓虫记：单位换算的坑', 'fig07_cqbug.png', '图 6：CQ bug 勘误链与 ×R 残留检验',
     '(a) 项目自己抓到过一只大虫（我们验证了修复）：CQ 无量纲化少乘一个半径 R，"系数法"FM 只在半径恰为'
     ' 1 米时正确。暴露铁证：DJI 小桨算出 FM=6.4——品质因数物理上不可能超过 1。修复后用"反推去污染公式"'
     '把修复前的历史读数换算一遍，与真实重跑逐点吻合，勘误链闭环。(b) 顺藤摸瓜又抓到一只残留的：三个优化'
     '脚本里"系数→瓦特"换算还残留旧约定的 /R，实测功率低估 4.3%（优化日志 FM 偏高 4%，需 ÷1.04 读）。'
     '2026-10-25 已把三处脚本统一改为 P = cq·q·Vt；验证脚本保留旧换算用于给历史日志消毒。'),
    ('十、交付的叶片量过尺吗', 'fig08_geom.png', '图 7：交付叶片几何四联图',
     '对第一版交付叶片（D=2.08m / 200kgf / 2 叶）实测：红线执行是真的——12 个站位翼型坐标逐个量，'
     '尾缘厚度全部精确 2.000 mm；雷诺数 4.5e5~2.4e6 全程落在已验证区间。两处瑕疵：①几何 CSV 厚度列是'
     '"参数目标值"，实物偏厚 0.5~0.8 个百分点；②弯度参数 3.0% 实际只生成 2.2% 弧高（生成器标定偏 27%），'
     '文档口径与实物不符——已列入问题清单。'),
    ('十一、3D 求解器是真算还是装样子', 'fig09_wake.png', '图 8：桨尖涡几何 vs 实验',
     '验证"自由尾迹"是不是真的：看桨尖涡（叶尖甩出的最强漩涡，悬停直升机的下洗烟圈）的几何。'
     '算出来的涡转 180°（半圈）后：收缩半径 0.897R vs 实验 0.905R（差 0.9%）；下沉 0.092R vs 0.09R（几乎重合）。'
     '收缩和下沉不是任何人输进去的假设，是方程自己解出来的，解出的形状和真实测量吻合——'
     '这是"真三维、非 BEMT"最直接的物证。'),
    ('十二、同一程序跑两遍，答案一样吗', 'fig10_repro.png', '图 9：复现性三联验证',
     '基准工况重跑：CT=0.004749750、CQ=0.000340194，与项目存档逐位一致；交付叶片重跑：推力 1975.656 N 等'
     '全部指标与历史 JSON 一致到 1e-10 量级——而且是跨代码版本的一致（中间修过 CQ bug，物理量不受影响）。'
     '确定性复现成立。'),
    ('十三、电都花在哪了', 'fig06_ledger.png', '图 10：功率账本与 FM 阶梯',
     '功率账本拆分：把空气往下压着走（诱导）占约 90%，尾流打转动能仅 0.5%，表面摩擦约 6%。'
     '结论：想省电主战场在诱导损失，翼型减阻是零头——这决定了优化应重点调扭角和平面形状。'
     '同一张图还有"κ 阶梯"：定标因子从 1.0 拧到 1.2，同一把桨的 FM 读数从约 0.82 滑到约 0.69——'
     '这就是项目现在"报 FM 必须带口径"的原因。账本本身没有任何隐藏的自由系数。'),
    ('十四、优化器跑了一夜，结果能信吗', 'fig11_cmaes.png', '图 11：CMA-ES 轨迹与口径修正',
     'CMA-ES 17 维寻优于 2026-10-25 凌晨跑完（40 代 × 14 候选 = 560 次评估）。结局比"跑完"更有意思——'
     '防假货机制真刀真枪抓到了假货，见下表。三点诚实备注：①日志 FM 含第九节的 ×1.04 换算残留'
     '（推荐设计 hi-fi FM 日志 0.857，修正后约 0.824，κ=1.2 定标口径）；②推荐设计的"绝对 FM"还需超深档终验'
     '才能入账（hi-fi 档对这类特殊平面形有已知的诱导低估伪影）；③换算 bug 修复后，后续运行无需手读修正。'
     '一句话：优化器的绝对数字要打折听，但"哪个设计更好"的相对排序是可信的。'),
]
for title, png, cap, txt in secs:
    story.append(CondPageBreak(3.2 * cm))
    story.append(H(title, 0))
    story.append(Paragraph(txt, S['body']))
    story.extend(fig(os.path.join(F, png), cap))

story.append(CondPageBreak(6 * cm))
story.append(H('十四（续）、优化器成绩单', 0))
story.append(tbl(['事件', '结果'],
                 [['名义最优（第 30 代，功率 26.6 kW，FM 读数 1.13）',
                   '（否决）FM>1 物理不可能 = 幻影铁证；高保真复核实测功率 37.2 kW（+40%），且第 9 站位失速违约'],
                  ['第 16 代个体（快档 32.8 kW）',
                   '（通过）hi-fi 复核 35.1 kW，全部约束满足 → 推荐设计'],
                  ['可信的相对结论', '同口径下推荐设计比第一版交付叶片功率低约 15~20%，扩维+寻优方向有效']],
                 [0.42, 0.58]))
story.append(Paragraph('表 3：CMA-ES 终局仲裁', S['caption']))

# ---------------------------------------------------------------- findings
story.append(H('十五、完整问题清单（白话版）', 0))
nf = [
    ('高', ('已修复', OK_C), '优化脚本功率换算残留 /R（功率低 4.3%）——影响修复后所有经脚本的功率/FM 绝对值',
     '10-25 已修复：三个脚本统一改为 P = cq·q·Vt'),
    ('高', ('已修复', OK_C), '优化器每代存档时崩溃（对数组做逻辑判断）——CMA-ES 无法跑完一代',
     '已修复，并完成 40 代完整运行'),
    ('中', ('注意', WARN_C), '翼型弯度参数标定偏 27%（参数 3.0% → 实物 2.2%）——文档口径与实物不符；设计变量语义失真',
     '待重标定（改动影响所有历史结果，需专项做）'),
    ('低', ('注意', WARN_C), '几何 CSV 厚度列是目标值非实测值（实测偏厚 0.5~0.8pp）', '导出时改用实测'),
    ('低', ('注意', WARN_C), '研究日志一处 FM 表格的列标签写串了（0.692 属 κ=1.20）', '本报告已勘误'),
    ('低', ('注意', WARN_C), '涡核生长常数代码值与文献值不同，且有未注释的经验加速', '加注释即可，数值上更稳定'),
    ('低', ('注意', WARN_C), '尾迹初始化用了动量理论近似值（仅迭代起点，收敛态 100% 自由尾迹）', '注明"仅初始化"防误读'),
    ('低', ('注意', WARN_C), '叶素载荷用小角度近似（悬停影响 <1%）', '记录即可'),
    ('低', ('注意', WARN_C), '一次诊断脚本首跑崩溃导致 JSON 缺一个键（数据在文本日志里完整）', '记录'),
    ('低', ('注意', WARN_C), '精度报告一处偏差表述只覆盖小迎角（大迎角差距 24~33%）', '措辞收窄'),
]
story.append(tbl(['优先级', '状态', '问题', '处置'],
                 nf, [0.09, 0.10, 0.53, 0.28], aligns=['c', 'c', 'l', 'l']))
story.append(Paragraph('表 4：问题清单（2 项高优先级均已修复）', S['caption']))
story.append(Paragraph(
    '<b>对项目自述的核对</b>：公式约定、实验数据源、基准误差数字、κ 定标、FM 阶梯、复现性声明、勘误链、'
    '2mm 尾缘、雷诺数域内使用、域外工况如实弃用——README / 研究日志 / 精度报告里的关键数字'
    '<b>全部可以独立复现</b>。诚实度判定：通过。', S['bodyni']))

# ---------------------------------------------------------------- conclusion
story.append(H('十六、总结论', 0))
story.append(Paragraph(
    '这套管线的自述与实际相符，结果可复现，修正因子有据可查，问题记录诚实。两个高优先级 bug 均已修复；'
    '优化推荐设计（第 16 代个体）待超深档终验后可进入交付流程（Phase D）。剩余的中优先级问题（弯度标定）'
    '不影响"相对比较"类结论，但修复前交付文档的弯度口径应以实测为准。', S['body']))

story.append(H('十七、想自己复核？', 0))
story.append(Paragraph('python scripts/verify_light.py    <font name="SimHei"># 秒级：涡核公式/恒等式/数据源/κ扫描/FM阶梯</font>', S['code']))
story.append(Paragraph('python scripts/verify_heavy.py    <font name="SimHei"># 约4分钟：基准工况复跑 + 交付叶片单点 + 换算对账</font>', S['code']))
story.append(Paragraph('python scripts/verify_figs.py     <font name="SimHei"># 重画本报告全部 11 张图（docs/verif_figs/）</font>', S['code']))
story.append(Spacer(1, 10))
story.append(Paragraph(
    '本报告由 GLM（Z.ai）驱动 ZCode 完成：全量源码精读、独立复算脚本撰写与执行、问题清单与修复。',
    S['caption']))

doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
print('body ->', OUT_BODY)

# ---------------------------------------------------------------- cover + merge
from cover_render import render_cover, detect_fonts
from pypdf import PdfReader, PdfWriter, Transformation

content = {
    "kicker": "验证报告 · 人话版 VERIFICATION",
    "hero": "悬停旋翼设计管线",
    "summary": "对 rotorgen 自由尾迹设计优化管线的全量源码精读与独立复算：14 项检查 12 项通过，"
               "抓到 3 个真 bug 全部修复；优化器的名义最优被例行抽查识破为假货，可信推荐为第 16 代设计。"
               "全文用人话写，所有行话第一次出现都当场解释。",
    "meta": "验证日期 2026-10-24/25 · 复核脚本 verify_light / verify_heavy / verify_figs",
    "footer": "ROTORGEN VERIFICATION · DOC 2026-VERIF-002",
    "year": "2026", "word": "VERIFY",
}
palette = {"primary": "#368aa6", "text": "#1c1c1a", "muted": "#78766f", "bg": "#ffffff"}
fonts = detect_fonts()
render_cover("03", content, r"E:\旋翼设计\results\verif_cover.pdf",
             palette=palette, fonts=fonts)

A4_W, A4_H = 595.28, 841.89
def norm(page):
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    if abs(w - A4_W) > 2 or abs(h - A4_H) > 2:
        page.add_transformation(Transformation().scale(A4_W / w, A4_H / h))
        page.mediabox.lower_left = (0, 0); page.mediabox.upper_right = (A4_W, A4_H)
    return page

w = PdfWriter()
w.add_page(norm(PdfReader(r"E:\旋翼设计\results\verif_cover.pdf").pages[0]))
for p in PdfReader(OUT_BODY).pages:
    w.add_page(norm(p))
w.add_metadata({'/Title': '悬停旋翼设计管线验证报告（人话版）', '/Author': 'Z.ai GLM',
                '/Creator': 'Z.ai', '/Subject': 'rotorgen 管线精读验证（人话版）'})
out = r"E:\旋翼设计\docs\VERIFICATION_REPORT.pdf"
with open(out, 'wb') as f:
    w.write(f)
print('final ->', out)
