# 规范依据

## Loop Engineering

- [Engineering the Loops that Replace Step-by-Step Prompting](https://arxiv.org/abs/2607.00038)：采用“触发、目标、验证、停止规则、记忆”的 loop specification，以及验证阶梯和命名终态。
- [Loop Engineering Guide](https://loopengineering.run/)：采用 discovery、handoff、verification、persistence、scheduling 五动作；实现者/验证者分离；发布保留人工门禁。

Loop Engineering 仍是快速演进的方法论，因此本目录把可验证的软件工程原则置于术语之上；若资料更新，必须通过 ADR 或变更记录调整，不得静默漂移。

## Qt / PySide6 官方依据

- [Qt for Python](https://doc.qt.io/qtforpython-6/)：PySide6 是 Qt 的官方 Python 绑定。
- [QMainWindow](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html)：主窗口、工具栏、Dock、状态栏及布局状态保存。
- [QNetworkAccessManager](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html)：异步网络 API、线程归属、请求与 reply 生命周期。
- [QThreadPool](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThreadPool.html) 与 [Qt 多线程技术](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-technologies.html)：后台任务、线程池与信号边界。
- [High DPI](https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-highdpi.html)：Qt 6 高 DPI 与多倍率资源。
- [QFont](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QFont.html)：字体族匹配和 `QFontInfo` 实际字体验证。
- [QAbstractItemModelTester](https://doc.qt.io/qtforpython-6/PySide6/QtTest/QAbstractItemModelTester.html)：模型一致性测试。
- [Qt for Python 与 PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)：PySide6 打包注意事项。

## 项目内依据

- `../AGENTS.md`：现有架构、数据、测试与交付约束；其中“仅标准库/Tkinter”已由已接受的 ADR-0001 和用户目标覆盖，但仓库级规则与依赖元数据仍待 WI-001 迁移。
- `../README.md`：当前功能与运行/打包合同。
- `../src/stock_advisor/`：当前行为的最终事实来源。
- `../tests/`：现有行为合同；Tk 专属断言不能直接证明 Qt 完成。

## 工具链候选（尚未批准或锁定）

- [PySide6 6.11.1](https://pypi.org/project/PySide6/)：当前验证起点，提供 Windows CPython 3.10+ abi3 wheel并列出 Python 3.14。
- [PyInstaller 6.21.0](https://pypi.org/project/pyinstaller/)：打包验证候选。
- [pytest 9.1.1](https://pypi.org/project/pytest/) 与 [pytest-qt 4.5.0](https://pypi.org/project/pytest-qt/)：现代测试栈候选。

这些版本只用于 WI-003 的隔离 spike；最终选择必须精确锁定、记录 hash、通过 Python 3.12/3.14 兼容矩阵与许可证人工门禁。
