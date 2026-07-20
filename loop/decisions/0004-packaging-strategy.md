# ADR-0004：PySide6 打包策略

- 状态：accepted
- 日期：2026-07-10（决策定档：2026-07-20，依据 EXP-001 实测）
- 人工门禁：HG-PACKAGING、HG-LICENSE

## 背景

REQ-029 要求 PySide6/PyInstaller/开发依赖精确锁定并完成许可证、安全、SBOM 审查；REQ-030 要求发布仍提供批准的 Windows 交付物（`股市锦囊.exe`/`使用说明.html`）并具有回滚路径。当前生产仍是 Tkinter + PyInstaller onefile，PySide6 版本、Qt 插件集合、EXE 体积和冷启动特征目前均未实测，RISK-002（PySide6 onefile 包体或冷启动不可接受）与 RISK-003（Qt platform/image/style 插件遗漏导致目标机失败）在没有 spike 数据前都无法证伪或证实。因此本 ADR 在测量完成前只记录"优先评估方向 + 决策规则"，不提前锁定最终打包形态，避免在没有数据支撑时就对用户承诺一个可能无法兑现的单文件交付合同。

## 决策

**采用 PyInstaller onedir/windowed**（`股市锦囊/股市锦囊.exe` + 同目录 Qt 运行时），随发布打包成一个 zip 分发；不再采用 onefile。EXP-001（EVD-QT-003）测量到齐后按下方"决策规则"重评，两条独立理由都指向 onedir：

1. **启动时间——onefile 不达标**。onefile 热启动 2.903s，已超过 `performance-budgets.json` 的 `warm_start_seconds` p95 ≤ 2.5s；冷启动只会更慢（onefile 每次启动都要把约 100 MB 运行时重新解压到临时目录）。onedir 热启动 0.685s，比 onefile 快 4.2 倍，对两条预算都有数倍余量。这正是决策规则里"onefile 无法满足冷启动门槛"的触发条件。
2. **LGPL 重链接义务——onedir 才履行得了**。PySide6/Qt 以 LGPL-3.0 交付，第 4(d) 条要求接收方能用修改过的库版本替换并重新链接。onedir 把 Qt DLL 以独立文件放在应用目录，用户替换即可满足；onefile 把它们压进单个可执行文件，实际上剥夺了这个能力，使合规论证变得脆弱。

体积不是决定因素：onefile 39.3 MB vs onedir 1.8 MB EXE + 99.9 MB 目录，两者都在可交付范围内（`single_file_exe_mib` 的 150 MiB 上限本就是给 onefile 形态的）。

**代价与缓解**：这改变了原先"单文件双击即用"的交付合同——用户拿到的是一个目录而非孤立 exe。缓解：发布物为 zip，解压后双击 `股市锦囊.exe` 即可，无需安装；这也是 Qt 桌面应用的通行形态。该变更须经 HG-PACKAGING/HG-LICENSE 人工门禁确认后方可正式发布。

## 目标

优先评估继续 PyInstaller onefile/windowed，最终仍输出 `股市锦囊.exe` 与 `使用说明.html`。

## 必须先测量

PySide6 精确版本组合、Qt plugins、EXE 大小、冷/热启动、RSS、构建时间、杀毒误报、许可证交付义务。

## 替代方案

- onedir：启动快、插件透明，但改变单文件合同。
- `pyside6-deploy`/Nuitka：需新工具链、许可证和可重复性评估。

## 决策规则

onefile 若无法满足 150MiB 暂定上限、4s 冷启动或插件稳定性，则提交量化证据给用户选择，不擅自改变交付合同。

## 后果

正面：优先复用现有 PyInstaller onefile 经验和现成 `build_exe.py` 流程；onefile 若测量达标，可以不改变现有单文件分发承诺，用户体验（双击即用、无需安装目录）不变。

负面 / 成本：PySide6 的 Qt 插件集合比 Tkinter 显著更重，onefile 若要满足 150MiB/4s 上限可能需要额外裁剪插件或改变解压缓存策略；决策悬而未决期间，下游打包相关工作项（WI-003、WI-006、WI-024）无法进入实现，必须先产出测量证据。

## 回滚

保留最后一个验证通过的构建流程和产物哈希。

## 重访触发

WI-003/WI-006 的 spike 测量数据到齐后（EXE 体积、冷/热启动、RSS、构建时间、杀毒误报、许可证清单），必须依据"决策规则"重新评审，把状态从 `proposed` 转为 `accepted` 或改采 onedir/其他方案；若 PyInstaller 上游放弃 onefile 支持，或 Qt 插件生态发生不兼容变化，同样需要重新评审。

## 关联

REQ-029、REQ-030、REQ-034、AC-009、AC-034、WI-003、WI-006、WI-024、WI-025、RISK-002、RISK-003。

