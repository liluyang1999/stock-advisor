# Loop 状态（机器渲染）

- Objective: `OBJ-001`
- Phase: `release_prep`
- Status: `active`
- Milestone: `MS-08`
- Selected work item: `WI-035` — 复刻 Tkinter 版 GUI 版式：卡片语言、八列结果表、因子条/光谱/解释三件套 (`verifying`)
- Baseline: `e827d840a791fc23bcdbd26b1424147820017d88`
- Dirty worktree: `true`
- GUI（现＝目标，Tk 生产层已随 WI-023 移除）: `PySide6`
- Runtime font target: `Microsoft YaHei`
- Tests: `912/912`
- Loop tooling tests: `59/59`
- Loop schemas: `23`
- Traceability: `34/34`
- Coverage: `0.96042`
- Release candidate: `false`
- Latest gate run: `LOOP-20260905-002`

## Next actions

- 本轮 UI、交互、教学与构建隔离验证见 EVD-LOOP-017/018；最终交付的来源提交和哈希以 dist/RELEASE_MANIFEST.json 为准。
- HG-LICENSE / HG-PACKAGING / HG-RELEASE 仍待原约定的人类签署，代码同步不代表正式发布。
- WI-032/033/035 的历史人工验收状态不由机器验证自动代签。
