# rotorgen — 端到端悬停旋翼自动设计与优化

**End-to-end automated hover-rotor design & optimization pipeline (UVLM-free-wake + self-built 2D panel/BL airfoil chain).**

> **Built with GLM (Z.ai)** — 本项目由 Z.ai 的 GLM 大模型驱动 ZCode 编码智能体全程研发：
> 求解器代码、基准验证、优化挂机、源码审计与文档撰写。

输入直升机旋翼的需求参数(直径 / 悬停推力 / 桨叶数 / 尾缘厚度),输出"翼型族 + 桨叶几何 + 三维气动验证"的完整悬停设计方案,悬停品质因数(FM)最大化。**全程无 BEMT**:所有诱导入流都来自自由尾迹涡系的 Biot–Savart 直接积分。

```
输入(D=2.08 m, T=200 kgf, B=2, 钝尾缘 2 mm)
 → CST 翼型族生成(2 mm 绝对尾缘厚度逐站位精确映射)
 → 自研 2D 面板法 + 边界层极线(Thwaites/Michel/Head,~3 ms/迎角)
 → 自由尾迹 3D 求解(UVLM 涡格 + PIPC 周期松弛 + Numba 并行,~10-60 s/工况)
 → 集体距二分配平至目标推力
 → Nelder-Mead 外环寻优 → 高保真复核 + 全几何/性能交付
```

## 文档(人话版,所有行话当场解释)

- **[全流程图解](docs/PIPELINE_GUIDE.md)**([PDF](docs/PIPELINE_GUIDE.pdf))— 总流程图 + 3D 内循环图 + 逐模块逻辑与算法说明书 + 名词小词典
- **[验证报告](docs/VERIFICATION_REPORT.md)**([PDF](docs/VERIFICATION_REPORT.pdf))— 14 项独立验证记分卡、3 个真 bug 的抓捕与修复记录、优化器"幻影最优"仲裁
- [FM 0.75 提升计划](docs/FM075_PLAN.md) · [研究日志(含所有失败与修复)](RESEARCH_AND_BENCHMARK_LOG.md) · [精度报告](docs/ACCURACY_REPORT.md)

## 为什么是这个方案

| 红线约束 | 本仓库的做法 |
|---|---|
| 禁止 BEMT / 动量入流 | 自由尾迹涡系 Biot–Savart 直接积分,尾迹收缩、桨-涡干扰、桨尖损失均为求解结果而非假设 |
| 钝尾缘物理厚度硬约束 | 2 mm 以绝对厚度注入 CST 参数化,逐站位实测核验 |
| 三维效应 + 优化环速度 | PIPC 伪隐式周期自由尾迹 + Numba `parallel=True`,单工况 10~60 s(URANS 同类验证为 40 CPU·h/转) |

## 基准验证(Caradonna–Tung,2 叶 σ=0.106,与设计同 regime)

核心工况(θ≥8°):**CT 误差 −5.6%~+14.7%,CQ 误差 −2.8%~+8.9%**,单工况 11 s。
域外算例(微型高实度 / 全尺寸低实度)偏差如实记录于 [研究日志 §2.2](RESEARCH_AND_BENCHMARK_LOG.md)。

2D 链对 NACA0012(Re 6e6):Cl_α 0.1126/deg(实验 0.109,+3.3%),Cp_min 误差 <2%,Cd 偏低 12~18%(简化边界层层级的文献预期,优化中已用 ×1.15 硬修正补偿)。

## 交付样例(D=2.08 m / T=200 kgf / B=2 / TE 2 mm)

- 推力 200.7 kgf(+0.4%),轴功率 46.7 kW,悬停 FM **0.649**(高保真档,1432 RPM / σ=0.178)
- 全展向尾缘厚度恒 2.000 mm(CSV 逐行核验),雷诺数范围 4.5e5~2.4e6
- 见 [`results/final/`](results/final/)(桨叶几何 CSV、12 站位翼型 .dat、三维叶面点云、性能 JSON、工程报告 PDF)

**诚实注记**:交付口径含保守记账因子(κ_B=1.2),功率账本审计显示同套叶片在物理口径下 FM≈0.76~0.79;两口径差异与修复路线见 [FM 0.75 提升计划](docs/FM075_PLAN.md) 与[研究日志 Phase 5](RESEARCH_AND_BENCHMARK_LOG.md)。

**最新进展(2026-10-25)**:17 维扩维参数化 + CMA-ES 多保真寻优完成 40 代 / 560 次评估。名义最优被"每 8 代高保真抽查"识破为快档**幻影最优**并否决;通过全部约束的推荐设计(gen16)同口径功率较第一版交付叶片低约 15~20%,待超深档终验(Phase D)。详见 [Phase C 报告](results/final_v2/PHASE_C_REPORT.md)与[验证报告 §14](docs/VERIFICATION_REPORT.md)。另:优化脚本功率换算的 /R 残留 bug 已于 10-25 修复。

## 快速开始

```bash
pip install -r requirements.txt   # Python 3.12+(开发环境 3.14)

# 复跑基准矩阵(Caradonna-Tung / Martin-Tung / Harrington)
python scripts/run_bench.py

# 端到端寻优(45+ 评估,约 40 分钟)→ results/final/
python scripts/design_opt.py
python scripts/finalize.py       # 高保真复核 + 交付物导出

# FM 0.75 口径诊断(当前状态审计)
python scripts/diag_fm075.py
```

依赖只用到 numpy / scipy / numba / matplotlib,无 CAE 商业软件。

## 目录结构

```
src/rotorgen/
  foil2d.py panel2d.py bl2d.py   # 自研 2D:涡面板 + 边界层极线
  famgen.py airfoil.py           # CST 翼型族(含 2mm 尾缘硬约束)
  kernels3d.py rotor3d.py        # 自由尾迹 3D 求解器(PIPC + Numba)
scripts/                         # 基准、寻优、交付、诊断
results/                         # 基准矩阵与最终设计交付物
docs/FM075_PLAN.md               # FM 0.75 路线图(口径修复→扩维→CMA-ES)
RESEARCH_AND_BENCHMARK_LOG.md    # 全程研究日志(含所有失败与修复)
```

## 关联仓库

- 基准数据(C-T / Martin-Tung / Harrington / UH-60A / DJI 9443 / APC / UIUC 等十套旋翼-螺旋桨基准及原始文献):[PuddingTower/rotor-propeller-benchmarks](https://github.com/PuddingTower/rotor-propeller-benchmarks),克隆到本仓库 `benchmarks/` 目录即可复跑。

## 致谢

- 本项目由 [GLM](https://z.ai)(Z.ai 训练的大语言模型)驱动 ZCode 编码智能体完成——包括全部求解器代码、基准验证、优化挂机、源码审计与文档撰写。
- 求解器方法论与文献溯源见 [RESEARCH_AND_BENCHMARK_LOG.md](RESEARCH_AND_BENCHMARK_LOG.md) §1.3(Bagai–Leishman PIPC、Caradonna–Tung 基准、CST 参数化等)。

## License

[MIT](LICENSE)
