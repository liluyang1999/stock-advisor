# ADR-0001：采用 PySide6 替代 Tkinter

- 状态：accepted
- 日期：2026-07-10
- 决策来源：用户明确要求
- 人工门禁：HG-ARCH（方向决策已通过本 ADR accepted；HG-ARCH 门禁本身对应仓库/源码对齐（WI-001）的人工签字，正式通过仍待 WI-001 执行完成后给出，目前状态为 pending；具体版本/发布仍需 HG-DEPS/HG-LICENSE）

## 背景

现有仓库要求运行期仅标准库/Tkinter，但最新用户目标明确指定 PySide6。用户当前指令优先，旧规则必须在正式迁移时同步更新。

## 决策

目标 GUI 使用 PySide6 Qt Widgets。迁移采用 strangler 方式，领域核心保持无 Qt。当前实现仍如实标注为 Tkinter，直到源码、测试和打包证据完成。

## 替代方案

- 继续 Tkinter：依赖最小，但不满足当前明确目标。
- Qt Quick/QML：视觉能力强，但增加语言/部署复杂度，当前数据工作台更适合 Widgets。
- Electron/Web：违反 Python 桌面和包体方向。

## 后果

正面：成熟 model/view、Dock/Splitter、可访问性、高 DPI、异步信号和桌面布局。

负面：运行依赖、包体/冷启动、插件、许可证、测试和构建复杂度显著增加。

## 迁移/回滚

按页面逐步迁移并共享领域核心；在 PySide6 全门禁通过前保留可运行 Tk 基线。回滚不得破坏现有配置 JSON。

## 重访触发

PySide6 与目标 Python/Windows 不兼容、许可证无法满足、onefile 不可接受、性能预算不可达。

