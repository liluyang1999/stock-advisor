# 质量门禁

## 当前实测基线

- CPython 3.14.4 / Windows 11 AMD64。
- 449 tests / 45.052s / OK。
- `main.py --self-test` exit 0 / SELF_TEST_OK。
- compileall exit 0。
- 覆盖率、lint、类型、Qt、clean package：未测量/未建立。

## 门禁顺序

1. **G-LOOP**：loop JSON/schema、追溯、精确状态渲染、backlog 投影、核心边界与控制脚本一致。
2. **G-FORMAT**：Ruff format 0 差异（工具批准后启用）。
3. **G-LINT**：Ruff 0 错误、0 未批准 warning。
4. **G-TYPE**：mypy strict 0 错误；可分阶段但发布全包。
5. **G-CORE**：纯逻辑/现有全量测试 100% 通过。
6. **G-COVERAGE**：`coverage run -m pytest` + `coverage report --fail-under=85`；全量 ≥90%/≥85%（行/分支）、核心 ≥95%/≥90%，见 `quality/convergence.json.coverage`（工具批准后启用）。
7. **G-NUMERIC**：黄金向量、性质、前视、确定性。
8. **G-NETWORK**：parser、deadline、fault matrix、无伪造 fallback。
9. **G-WORKFLOW**：FakeProvider 集成、部分失败/停止。
10. **G-QT-MODEL**：QAbstractItemModelTester、排序/过滤/增量。
11. **G-QT-GUI**：offscreen 交互、signals、取消/迟到/销毁。
12. **G-VISUAL**：Windows DPI/字体/视觉状态矩阵（offscreen 证据不能替代真实 Windows 视觉验证）。
13. **G-PERF**：启动、RSS、event P95、5000 行表格、图表。
14. **G-SECURITY**：依赖漏洞、导出注入、路径、日志脱敏。
15. **G-LICENSE**：PySide6/Qt/PyInstaller/SBOM/NOTICE 人工复核。
16. **G-BUILD**：clean PyInstaller、dist 清单、插件/资源。
17. **G-EXE**：EXE self-test + Windows 冒烟。
18. **G-TRACE**：REQ/AC/WI/TEST/EVD 100% 追溯。
19. **G-RELEASE**：连续 5 次全绿 + HG-RELEASE。

每个门禁对象在 `quality-gates.json` 中携带 `owning_work_item`（启用它的工作项；尚不存在的工具类工作项——G-FORMAT/G-LINT/G-TYPE/G-COVERAGE——暂以 `WI-000` 占位，`note` 字段说明其真实归属在 WS-8/Plan 5）。

## 硬指标

- 必需测试：100% pass，0 failure/error，0 未批准 skip。
- 全生产代码行覆盖 ≥90%、分支 ≥85%。
- 核心模块行覆盖 ≥95%、分支 ≥90%。
- Qt controller/model/presenter 行 ≥90%、分支 ≥85%。
- P0/P1/P2 开放缺陷 = 0。
- `fabricated_fallbacks = 0`、`late_result_overwrites = 0`。
- 需求追溯和证据覆盖 = 100%。
- 免责声明在关键结果/导出覆盖 = 100%。

## 证据规则

每次运行保存 command、cwd、environment、commit、dirty、start/end、exit_code、summary、artifact hash、verifier。未保存原始报告时不得声称达到覆盖率或性能。

完整机器定义见 `quality-gates.json`。
