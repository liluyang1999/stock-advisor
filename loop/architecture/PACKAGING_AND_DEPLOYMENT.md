# 打包与部署

## 当前合同

- `build/` 仅中间产物。
- `dist/` 仅最终 `股市锦囊.exe` + `使用说明.html`。
- onefile、windowed。
- EXE `--self-test` 退出 0 并含 `SELF_TEST_OK`。

PySide6 迁移是否继续 onefile 由 ADR-0004 和 HG-PACKAGING 决定；未批准前不改变用户合同。

## clean build

1. 新建项目内隔离环境（实际策略待批准）。
2. 从精确锁文件安装 Python/PySide6/PyInstaller。
3. 验证无系统 PySide6/Shiboken 混入。
4. 跑 format/lint/type/test/coverage/Qt/fault/performance。
5. 清理并验证 build/dist 解析路径仍在项目内。
6. 构建 Qt plugins/resources/QSS/icon/translations。
7. EXE self-test、Windows GUI 冒烟、字体/DPI/网络降级。
8. 生成 SHA-256、SBOM、许可证/NOTICE 和构建元数据。

## Qt 资产清单

- platform plugin（Windows）。
- 必需 imageformats/styles（按实际使用最小化）。
- resources.qrc、SVG/多倍图标、QSS。
- 不捆绑系统 Microsoft YaHei 字体文件；运行时验证系统字体。
- offscreen 插件仅开发/测试按需收集。

## 预算

首个 spike 测量 EXE 大小、冷/热启动、RSS；在 HG-PACKAGING 批准后冻结预算。暂定 onefile 上限 150MiB，但不能代替实测和许可决策。

## 回滚

保留最后一个通过全门禁的 Tk 或 PySide6 发布包、哈希和说明。配置 schema 必须向后兼容；若 UI 回滚，用户自选/持仓不得丢失。

