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

## 分发安全（代码签名 / SmartScreen / Qt LGPL 归属）

本节记录 Windows EXE 对外分发前必须解决的两类供应链/合规义务的**计划与归属**，不代表已经实现——产品已是 PySide6 onedir 交付并捆绑 Qt 二进制（WI-024），但代码签名证书与 NOTICE 正文仍待人工发布门禁（HG-LICENSE/HG-PACKAGING/HG-RELEASE）落定；提前编造签名证书细节或 NOTICE 正文内容会违反"不伪造证据"原则，因此这里只锁定目标形态、决策路径和责任工作项。

### 代码签名与 SmartScreen 来源信誉

- **现状**：`股市锦囊.exe` 当前未签名；未采购代码签名证书；`HG-LICENSE`/`HG-PACKAGING`/`HG-RELEASE` 均未触发（产品尚未对外发布）。
- **目标形态（待 `HG-LICENSE` 批准，非当前实现）**：使用 Authenticode 对最终 `dist/股市锦囊.exe` 签名（证书类型、密钥保管方式——如 HSM/云 KMS 而非本地明文私钥文件——及签名时间戳服务器的选择留待批准时确定），使 Windows SmartScreen 能建立发布者信誉。
- **已知约束**：SmartScreen 信誉需要同一签名身份积累下载量与时间，**首次或低分发量阶段仍会出现"Windows 已保护你的电脑"式未知发布者提示**，这是预期状态而非缺陷；`使用说明.html` 必须明确告知用户这一现象及如何核实发布者/哈希，不得引导用户关闭 SmartScreen 或以其他方式绕过系统安全控件。
- **未签名阶段的分发披露**：在签名方案被 `HG-LICENSE`/`HG-RELEASE` 批准并实际生效前，任何形式的分发都必须在 `使用说明.html`/README 中明确声明"当前构建未经代码签名"，并提供 SHA-256 供用户自行核验，不得静默隐藏未签名状态。
- **归属**：证书采购、签名流水线接入 `scripts/build_exe.py` clean build 步骤、SmartScreen 信誉积累策略，归属 `WI-025`（许可证/SBOM/连续全绿/发布门禁），受 `HG-LICENSE` 与 `HG-RELEASE` 双重人工门禁约束；本次治理加固只记录计划，不新增签名相关产品代码或采购行为。

### Qt LGPL NOTICE / 第三方许可归属

- **义务来源**：PySide6 采用 LGPLv3（或项目最终经 `HG-LICENSE` 批准的商业许可，见 `governance/DEPENDENCY_POLICY.md`"PySide6 特别规则"），LGPL 分发通常要求提供第三方许可证全文/版权声明，并保留用户替换受 LGPL 约束的库的可行路径——后者与 onefile 单文件打包是否可行存在已知张力，属于 `ADR-0004`（打包策略）与 `HG-PACKAGING` 的决策范围，本节不重新展开该权衡，只记录 NOTICE 本身的归属。
- **计划形态**：`scripts/build_exe.py` 的 clean build 流程（见"clean build"第 8 步"生成 SHA-256、SBOM、许可证/NOTICE 和构建元数据"）产出一份 `NOTICE.txt`/`THIRD_PARTY_LICENSES.txt`，随 `dist/` 一并分发，内容至少覆盖 PySide6/Qt、PyInstaller 及其传递依赖的许可证全文或可核验链接与版权声明。
- **明确 deferral（本次不实现的理由）**：产品尚未进入 PySide6 实际迁移，当前不存在真实的 Qt 二进制/传递依赖清单可供生成准确 NOTICE；在此之前编造 NOTICE 正文属于伪造合规文档，比不写更危险。因此本节只确定"必须做什么（NOTICE 生成与人工复核）、卡在哪个门禁（`G-LICENSE`）、由谁做（`WI-025`）"，具体 NOTICE 内容生成、许可证文本采集与人工复核在 `WI-025` 实际执行时落地。
- **归属**：`WI-025`；门禁 `G-LICENSE`（`quality/quality-gates.json`，`pass_condition: "human gate HG-LICENSE accepted"`）。

