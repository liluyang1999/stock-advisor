# 仓库清单（2026-07-10）

## 入口与交付

| 路径 | 当前职责 |
|---|---|
| `../main.py` | GUI / `--self-test` 入口、Tk DPI 设置 |
| `../build_exe.py` | PyInstaller onefile/windowed 构建、HTML 说明书生成 |
| `../run.bat`, `../run.sh` | 本地启动 |
| `../build.bat`, `../build.sh` | 构建 |
| `../requirements-build.txt` | 当前仅声明 `pyinstaller>=6.15` |
| `../assets/a_stock_strategy.ico` | Windows 应用图标 |
| `../dist/股市锦囊.exe` | 历史构建产物；未证明对应当前工作树 |
| `../dist/使用说明.html` | 历史说明书产物 |

## 源码

生产包位于 `../src/stock_advisor/`，共 22 个模块，按层拆成 4 个子包（ADR-0007）：`domain/`（12，纯核心）、`data/`（2）、`services/`（2）、`ui/`（6）；另有 5 个 `__init__.py` 包标记（根包 1 个 + 每个子包各 1 个）。领域、网络、流程、视图格式与 Tk GUI 已基本分层，但 `ui/app.py` 仍同时承担视图、控制器、任务生命周期、缓存、对话框和绘制。

完整模块职责见 `module-map.json`。

## 测试

- 23 个 `test_*.py` 模块。
- 449 个 `unittest` 测试方法。
- 187 项强绑定 Tk GUI 结构（`test_gui_layout.py` 116、`test_ui_polish.py` 71）。
- 262 项主要覆盖领域、网络解析、流程、持久化、格式化、入口和构建配置。
- 当前没有 CI、覆盖率、lint、类型检查或 PySide6 GUI 测试。

## 文档与设计资产

- `../docs/superpowers/specs/`：历史规格。
- `../docs/superpowers/plans/`：历史实施计划。
- `../docs/ui-concepts/`：UI 效果图；属于设计参考，不是运行完成证据。
- `../README.md`：当前 Tkinter/标准库运行合同。

## 工作树状态

基线提交 `881099806deca77a7bf7e784d6786f9bccdf0ce6`，分支 `main`。审计时已有未提交 UI 修改和新 UI 概念图；这些改动属于用户，后续迁移必须保留并先建立可恢复边界。

