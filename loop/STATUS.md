# Loop 状态（机器渲染）

- Objective: `OBJ-001`
- Phase: `release_prep`
- Status: `active`
- Milestone: `MS-08`
- Selected work item: `WI-035` — 复刻 Tkinter 版 GUI 版式：卡片语言、八列结果表、因子条/光谱/解释三件套 (`verifying`)
- Baseline: `881099806deca77a7bf7e784d6786f9bccdf0ce6`
- Dirty worktree: `true`
- GUI（现＝目标，Tk 生产层已随 WI-023 移除）: `PySide6`
- Runtime font target: `Microsoft YaHei`
- Tests: `874/874`
- Loop tooling tests: `59/59`
- Loop schemas: `23`
- Traceability: `34/34`
- Coverage: `0.9582`
- Release candidate: `false`
- Latest gate run: `LOOP-20260711-003`

## Next actions

- complete WI-035 verification (Tk 视觉基线回归的最终核验)
- close out WI-025 release readiness: 许可证/SBOM/连续全绿/发布门禁
- adjudicate WI-032 (pure_preserved 合同：layout.py 已退役，view_text.py 保留) 与 WI-033 (BoundedUrllibProvider 接入)
