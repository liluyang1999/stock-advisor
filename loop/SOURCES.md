# 规范依据

## 验证方法与状态

本文件区分两类条目：**已核实来源**（本目录曾实际发起网络请求，核对过链接可解析且内容与引用的论断相符）与**参考/启发（inspiration，非已核实引用）**（内容取自记忆或未能重新核对，只能作为思路来源，不得当作可审计的外部证据）。任何在本文件中新增或修改的外部引用，必须先尝试核实，核实失败或无法核实时必须使用"参考/启发"框架标注，不得直接断言为已核实来源——这是 `governance/ENGINEERING_RULES.md`"不伪造证据"原则在文档引用上的具体落地，伪造"已核实"比不核实更严重。

下方标注"（已核实 2026-07-13）"的条目，均在当日通过实际网络请求重新核对：论文/站点条目核对了标题、作者或核心论断与本文引用是否一致；PyPI 条目核对了 `pypi.org` 页面或 JSON API 返回的 `info.version` 是否等于本文引用的版本号。这类核实是**某一时刻的快照**，不等于永久事实——尤其 PyPI"当前最新版本"会随时间推移不再是最新，使用者引用本文件时若已过去较久，应重新核实而非直接信任日期标注；`WI-003`/`WI-006` 做最终依赖锁定前必须重新核实一次，不能沿用本文档的核实结果作为锁定依据。

## Loop Engineering

- [Stop Hand-Holding Your Coding Agent: Engineering the Loops that Replace Step-by-Step Prompting](https://arxiv.org/abs/2607.00038)（已核实 2026-07-13：标题、作者 Sandeco Macedo、"trigger/goal/verification/stopping rule/memory 五要素 + 验证阶梯"的核心论断均与本文引用一致）：采用"触发、目标、验证、停止规则、记忆"的 loop specification，以及验证阶梯和命名终态。本目录 `LOOP_PROTOCOL.md` §2 的六要素表在这五要素之外新增了项目自定义的"Authority"一行，是本项目对该论文模型的扩展，不是论文原文的一部分，避免读者误以为六要素全部来自论文。
- [Loop Engineering Guide](https://loopengineering.run/)（已核实 2026-07-13：站点核心论断"discovery/handoff/verification/persistence/scheduling 五动作"与"generator/evaluator 分离"均与本文引用一致）：采用 discovery、handoff、verification、persistence、scheduling 五动作；实现者/验证者分离；发布保留人工门禁。

Loop Engineering 仍是快速演进的方法论，因此本目录把可验证的软件工程原则置于术语之上；若资料更新，必须通过 ADR 或变更记录调整，不得静默漂移。两篇来源使用的词汇不完全相同（"trigger/goal/verification/stop rule/memory" 对 "discovery/handoff/verification/persistence/scheduling"），本目录 `governance/GLOSSARY.md` 的"Loop"词条是把两者与本项目实际运行的 `loop.json.cycle`（`observe→specify→decide→plan→implement→verify→review→learn→advance` 九阶段）调和为一份定义后的结果，遇到冲突以 `GLOSSARY.md` 的调和版本 + `LOOP_PROTOCOL.md` §2/§3 的具体机制为准，不再逐字复述任一来源原文当作本项目的定义。

## Qt / PySide6 官方依据

以下 `doc.qt.io` 链接（已核实 2026-07-13：逐一实际请求，均可解析，页面标题/导航面包屑与引用的类名或主题一致，未见 404）：

- [Qt for Python](https://doc.qt.io/qtforpython-6/)：PySide6 是 Qt 的官方 Python 绑定。
- [QMainWindow](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html)：主窗口、工具栏、Dock、状态栏及布局状态保存。
- [QNetworkAccessManager](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html)：异步网络 API、线程归属、请求与 reply 生命周期。
- [QThreadPool](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThreadPool.html) 与 [Qt 多线程技术](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-technologies.html)：后台任务、线程池与信号边界。
- [High DPI](https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-highdpi.html)：Qt 6 高 DPI 与多倍率资源；该链接固定指向 6.10 系列文档快照，与下方"工具链候选"引用的 PySide6 6.11.1 不是同一小版本，仅代表 High DPI 章节内容跨小版本通常稳定，不代表已核实 6.11.1 文档树本身。
- [QFont](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QFont.html)：字体族匹配和 `QFontInfo` 实际字体验证。
- [QAbstractItemModelTester](https://doc.qt.io/qtforpython-6/PySide6/QtTest/QAbstractItemModelTester.html)：模型一致性测试。
- [Qt for Python 与 PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)：PySide6 打包注意事项。

## 项目内依据

以下均为仓库内部路径，核实方式是确认文件/目录存在于本仓库（不是外部网络引用，因此不适用上面的"已核实/参考启发"网络核实框架，但仍需保持指向存在）：

- `../AGENTS.md`：现有架构、数据、测试与交付约束；其中"仅标准库/Tkinter"已由已接受的 ADR-0001 和用户目标覆盖，但仓库级规则与依赖元数据仍待 WI-001 迁移。
- `../README.md`：当前功能与运行/打包合同。
- `../src/`：当前行为的最终事实来源。
- `../tests/`：现有行为合同；Tk 专属断言不能直接证明 Qt 完成。

## 工具链候选（尚未批准或锁定）

- [PySide6 6.11.1](https://pypi.org/project/PySide6/)（已核实 2026-07-13：PyPI 页面 `info.version`/发布历史确为 6.11.1，2026-05-13 发布，含 `pyside6-6.11.1-cp310-abi3-win_amd64.whl`/`win_arm64.whl`，classifiers 含 Python 3.14）：当前验证起点，提供 Windows CPython 3.10+ abi3 wheel并列出 Python 3.14。
- [PyInstaller 6.21.0](https://pypi.org/project/pyinstaller/)（已核实 2026-07-13：PyPI 页面确为当前版本，2026-06-13 发布）：打包验证候选。
- [pytest 9.1.1](https://pypi.org/project/pytest/)（已核实 2026-07-13：PyPI 页面确为当前版本，2026-06-19 发布）与 [pytest-qt 4.5.0](https://pypi.org/project/pytest-qt/)（已核实 2026-07-13：`pypi.org/pypi/pytest-qt/json` 的 `info.version` 确为 `4.5.0`）：现代测试栈候选。

这些版本只用于 WI-003 的隔离 spike；最终选择必须在锁定当下重新核实（而非引用本文件的 2026-07-13 快照）、精确锁定、记录 hash、通过 Python 3.12/3.14 兼容矩阵与许可证人工门禁。
