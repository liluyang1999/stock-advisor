# ADR-0004：PySide6 打包策略

- 状态：proposed
- 日期：2026-07-10
- 人工门禁：HG-PACKAGING、HG-LICENSE

## 目标

优先评估继续 PyInstaller onefile/windowed，最终仍输出 `股市锦囊.exe` 与 `使用说明.html`。

## 必须先测量

PySide6 精确版本组合、Qt plugins、EXE 大小、冷/热启动、RSS、构建时间、杀毒误报、许可证交付义务。

## 替代方案

- onedir：启动快、插件透明，但改变单文件合同。
- `pyside6-deploy`/Nuitka：需新工具链、许可证和可重复性评估。

## 决策规则

onefile 若无法满足 150MiB 暂定上限、4s 冷启动或插件稳定性，则提交量化证据给用户选择，不擅自改变交付合同。

## 回滚

保留最后一个验证通过的构建流程和产物哈希。

