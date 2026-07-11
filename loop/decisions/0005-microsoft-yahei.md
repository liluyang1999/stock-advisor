# ADR-0005：全局字体采用 Microsoft YaHei

- 状态：accepted
- 日期：2026-07-10
- 决策来源：用户明确要求

## 决策

所有应用可控制的可见文字统一使用 `Microsoft YaHei`，包括 QWidget、菜单、tooltip、对话框、表格、图表、自绘文字和 HTML 说明书。创建 `QFont("Microsoft YaHei")` 后用 `setPointSizeF()` 设置小数点字号，在 QApplication 级应用，并由 QFontInfo 验证实际字体。Windows 原生标题栏字体由操作系统控制，是唯一明确例外。

## 字号

caption 9pt、body/control 10.5pt、section 13pt、page 17pt；任何辅助文字不低于 9pt。

## 后果

目标平台限定 Windows 字体可用性；不得打包系统字体文件。若字体缺失，发布前失败并明确环境要求，不能静默使用其他字体后仍宣称通过。

## 回滚/重访

只有用户批准新的字体合同才可修改。高 DPI 截断通过布局/token 修复，不用缩小字号规避。
