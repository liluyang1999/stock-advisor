# PySide6 迁移计划

## 阶段 0：保护基线

- 记录工作树和 449 测试基线。
- 建立 Tk 行为合同映射表。
- 不覆盖用户当前 UI 修改。

## 阶段 1：可交付性 spike

- 在批准的隔离环境精确安装 PySide6。
- 最小 QApplication/QMainWindow，验证 Microsoft YaHei、DPI、资源和 offscreen。
- 最小 PyInstaller 构建，测量 plugins/包体/启动/RSS/许可。
- ADR-0003/0006 已接受；通过 WI-009/EXP-003 验证实现合同，通过 WI-006 实测后再决定 ADR-0004。

## 阶段 2：骨架

- 建 `qt_app/`、session state、controller/worker signals、theme token。
- 建 QMainWindow/QStackedWidget/QStatusBar。
- 旧 Tk 入口仍可运行，Qt 入口以 feature flag/独立入口验证。

## 阶段 3：纵向切片

按“个股最小闭环 → 完整个股 → 筛选 → 组合 → 预警/深度工具”迁移。每个切片包含 UI、状态、线程、错误、测试和截图，不只搭空壳。

## 阶段 4：切换

- 187 个 Tk 合同全部映射。
- main.py 默认 Qt；`rg tkinter src` 无结果后删除旧 UI。
- 更新 README、AGENTS、依赖、构建和说明书。

## 阶段 5：收敛

运行完整门禁、连续稳定性、clean package、EXE self-test、真机 DPI/字体/网络降级、许可和回滚演练。

## 每步退出条件

`implemented` 仅代表代码存在；只有对应 `TEST-*` 和 `EVD-*` 通过独立复核才能进入下一阶段。
