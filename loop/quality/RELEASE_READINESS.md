# 发布就绪检查

状态记于 2026-07-20，对应提交 `8991ad5`（WI-025 产品侧）。勾选项均有证据 id 或可复跑命令；
未勾选项就是未完成，不做"实质上算完成"的解释。

## 规格与决策

- [x] AC-001..010 全部有 EVD。34/34 需求连上证据（`check_traceability.py` → `TRACEABILITY_OK 34/34`）。
- [x] ADR-0001..0006 需要接受的均已接受（14 份 ADR 全部 `accepted`；decisions.jsonl 的最新事件与文档一致）。
- [x] 无过期假设、风险或豁免。豁免登记簿为空；ASM-002 已按实测证伪；10 条风险全部处置（7 closed / 2 mitigated / 1 monitoring），无一停留在未处置的 `open`。

## 代码与测试

- [x] 核心无 Qt/Tk 依赖。G-CORE 门禁 + TEST-ARCH-002 的 AST 全量扫描。
- [x] 生产无 Tkinter。WI-023 删除 10 个 Tk 文件；生产源零 `tkinter` import 由 AST 扫描强制。
- [x] 全门禁 100% 通过，覆盖率达标。`run_gates.py` → `ran=7 failed=0`；语句 97.12% / 分支 93.54%。
- [x] Tk 187 行为合同映射 100%（WI-002：156 qt_replaced / 24 pure_preserved / 7 approved_retired）。
- [x] race/fault/DPI/font/perf 证据完成（EVD-QT-014 / EVD-NET-002 / EVD-QT-016 / EVD-PERF-001）。

## 构建与合规

- [x] 精确锁文件、干净环境、同一提交。构建脚本 `--clean`；清单记录 source.commit 与构建工具链版本。
- [x] Qt plugins/resources/QSS/icon 完整。WI-024 打包产物含全套插件目录，真机冒烟零 stderr（RISK-003 已证伪）。
- [ ] **SBOM、许可、NOTICE、漏洞、SHA-256。** SBOM（CycloneDX 1.5）、NOTICE、203 个文件的 SHA-256 与目录合并摘要均已产出；**缺 `licenses/GPL-3.0.txt`**——LGPL-3.0 正文声明它并入 GPL-3.0 条款，两份都要随附。`make_release_manifest.py` 因此以退出码 1 拒绝转绿。取自 https://www.gnu.org/licenses/gpl-3.0.txt 放进 `licenses/` 后重跑即可。
- [x] dist 仅批准产物。`make_release_manifest.py --verify` 对多出来的文件同样报错。
- [x] EXE self-test、Windows 冒烟。打包 EXE `--self-test` 0.49s 退出 0；真机 GUI 存活 6s 零 stderr（EVD-PKG-002）。

## 产品

- [x] 所有失败/降级明确，不伪造。故障矩阵覆盖限流/超时/字段漂移/半截响应，一律降级为可见提示。
- [x] 免责声明覆盖所有关键页面与导出。四条导出路径共用同一页脚，静态扫描零遗漏（TEST-DISC-001）。
- [x] 帮助和 README 与 PySide6 实际一致（WI-025：README/AGENTS.md/pyproject/CI 同步；AC-011）。
- [x] 配置兼容和回滚演练通过。配置往返含 Decimal 成本精确复原（TEST-QT-PORT-001）；回滚校验路径为 `--verify`，对内容改动、缺文件、多文件三类偏差分别报错（TEST-REL-001）。

## 人工门禁

自动化不得替代这三处签署（RELEASE_PLAN.md）。目前三处均未签。

- [ ] HG-LICENSE —— 需先补齐 GPL-3.0 正文，再由人确认许可选择与 NOTICE 表述。
- [ ] HG-PACKAGING —— 交付形态由单文件改为应用目录（ADR-0004），该合同变更需人工确认。
- [ ] HG-RELEASE —— 发布本身。
