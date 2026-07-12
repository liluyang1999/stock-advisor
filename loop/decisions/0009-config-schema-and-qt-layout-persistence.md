# ADR-0009：配置 schema 版本化与 Qt 布局持久化

- 状态：accepted
- 日期：2026-07-13

## 背景

REQ-009 要求配置跨会话持久化并兼容现有 JSON。`architecture/PERSISTENCE_AND_CONFIG.md`（Task 1 产出）已经给 `AppConfig` 定义了基线 schema（`product/app-config.schema.json`），并新增 `schema_version` 字段作为"本次治理新增的前瞻性约定"，文档原文明确写着"上表 schema 里的 `schema_version` 是 ADR-0009 将要落地的前瞻契约"——也就是说该文档和 schema 已经预支了本 ADR 的编号，本 ADR 正式补上这份被预支的决策记录。

同一份文档的"Qt 布局状态"一节又留了另一处未决决策："窗口 geometry、dock state……可使用 QSettings 或独立文件，但必须另立 ADR、检查 status/sync 和原子性"——本 ADR 一并解决这第二个悬而未决的问题。两者合并为一个 ADR，是因为它们都属于"持久化落地形态"这同一个决策维度（业务配置与 UI 状态各自用什么版本化和存储策略），而不是因为两者在技术实现上耦合。

## 决策

1. **schema_version**：`AppConfig` 持久化 JSON 引入字符串字段 `schema_version`（当前基线值 `"1.0.0"`，定义见 `product/app-config.schema.json`）。`parse_config()` 必须把缺失该字段的既有文件隐式当作"1.0.0 之前"的形状继续解析，不得因为字段缺失就拒绝加载或清空其余合法字段；`services/store.py` 一旦开始写出该字段，后续任何破坏性字段变更（改名、改类型、删字段）都必须递增版本号，并配一个逐版本、幂等、可回滚的迁移函数。
2. **Qt 布局持久化**：窗口 geometry、dock/splitter 状态采用**独立于业务配置的 JSON 文件**（例如 `%APPDATA%\股市锦囊\ui_state.json`，与 `config.json` 同目录，沿用同一套 `config_path()` 风格的路径解析和 `STOCK_ADVISOR_CONFIG` 同族测试覆盖约定），复用与 `config.json` 相同的原子写入流程（同目录临时文件 → flush →`os.replace`），并拥有自己独立的 `schema_version`（不与 `AppConfig.schema_version` 同步递增，两者是不同的版本轴）。默认布局必须始终可从零恢复：该文件缺失或损坏时回退到默认 geometry，不崩溃、不阻塞启动。
3. 不采用 QSettings 承载 Qt 布局状态（含 NativeFormat 与 IniFormat 两种变体）。

## 替代方案

1. **（Qt 布局）采用 QSettings 的 NativeFormat，即 Windows 下的注册表（拒绝）**：是 Qt 官方推荐的窗口状态持久化 API，省去自己实现 geometry 序列化的样板代码；但注册表写入与项目现有"配置和状态都是可读、可诊断、可在测试中重定向到临时路径的 JSON 文件"这一贯穿全项目的约定不一致——测试要重定向注册表写入需要额外的 mocking 层，而不是现有 `STOCK_ADVISOR_CONFIG` 式的路径覆盖就能解决；注册表内容也不便于用户手工诊断或备份。
2. **（Qt 布局）采用 QSettings 的 IniFormat，强制走 ini 文件而非注册表（拒绝）**：避免了注册表问题，形式上退化成"由 Qt 帮你管理一个 ini 文件"；但 QSettings 自身的写入/`sync()` 时机和原子性语义不如项目已经在 `store.py` 里验证过的"临时文件 + `os.replace`"模式明确可控，等于引入第二套语义不同、尚未经过项目自己测试验证的持久化技术，却没有换来相对于"直接复用现有原子写入 JSON 模式"的实际好处。
3. **（Qt 布局，采用）独立 JSON 文件 + 复用现有原子写入模式**：与 `config.json` 使用同一套已经过测试验证的读写基础设施（原子替换、损坏/缺失回退默认、测试路径重定向），只是另开一个文件和独立版本号，避免布局状态的 schema 演化牵动业务配置的 `schema_version`；代价是需要自己写窗口 geometry 的序列化/反序列化，但这部分逻辑远比"验证一个新持久化技术的原子性和可测试性"简单。
4. **（schema_version，拒绝）不引入版本号，仅靠字段级容错**：`parse_config()` 现有的"每字段独立校验、非法值回退默认"式解析确实已经能兼容大部分新增可选字段，但一旦出现字段改名或语义变更（而非单纯新增），没有版本号就无法区分"这是旧格式的字段 X"还是"这是新格式里含义不同的字段 X"，迁移函数也无从判断该对哪个版本的输入生效。
5. **（schema_version，采用）引入 `schema_version` 且新文件立即写出该值，旧文件隐式视为版本前形状**：见"决策"第 1 条。

## 后果

正面：

- 业务配置（`config.json`/`AppConfig`）与 UI 布局状态（`ui_state.json`）拥有各自独立的版本演化节奏，窗口 geometry 的一次调整不会强迫 `AppConfig.schema_version` 跟着递增，反之亦然。
- Qt 布局持久化复用 `config.json` 已经过 449 个产品测试验证的原子写入/损坏回退/测试路径重定向基础设施，不需要为一个新技术（QSettings）重新证明这些性质。
- `schema_version` 给未来任何破坏性 `AppConfig` 字段变更提供了可判定、可迁移的锚点，避免未来只能靠猜测兼容旧文件。

负面/成本：

- 需要新增并维护一个独立文件（`ui_state.json`）及其读写路径、原子写入和测试隔离，比"窗口每次以默认布局启动、什么都不持久化"多一份实现和测试面；该实现属于具体工作项（如 WI-015）的执行内容，本 ADR 不新增或修改产品代码。
- 放弃 QSettings 意味着放弃它内建的跨平台后端切换能力（macOS/Linux 各自的原生存储），但本项目目标发行形态是 Windows EXE（`architecture/PACKAGING_AND_DEPLOYMENT.md`），跨平台原生集成当前不是需求；若未来项目扩展到其他平台需要重新评估。
- `schema_version` 字段截至本 ADR 记录时仍是前瞻契约：`services/store.py::config_to_dict()` 尚未实际写出该字段（`PERSISTENCE_AND_CONFIG.md` 已明确此现状），本 ADR 记录的是目标形状而非已完成的实现；实际写出行为、`parse_config()` 的兼容处理与相应测试仍需具体工作项落地。

## 回滚

若独立 `ui_state.json` 文件方案在实现中被证明有问题（例如与 `config.json` 共享目录造成用户混淆，或原子写入在高频窗口 resize 时产生不可接受的 IO 压力），回滚路径是把窗口状态并入 `config.json` 本身作为一个可选子字段，不再独立成文件——两者已经共享同一原子写入实现，合并只需改变"写到哪个路径"，不需要改变写入机制本身。`schema_version` 字段的回滚是：若迁移函数被证明无法保持向后兼容，暂停对该字段的新版本递增，`parse_config()` 继续把所有文件当作隐式无版本形状解析，不阻塞现有功能。停止条件：若任一方案在实现阶段导致 449 个产品测试或 `--self-test` 无法保持绿色，必须先回退到"不引入该功能"的最小状态，再排查具体原因。

## 重访触发

- 若产品未来扩展到 macOS/Linux 分发，需要重新评估 QSettings 的跨平台后端集成价值。
- 若 `AppConfig` 出现第一次真正的破坏性字段变更（改名/改类型/删字段），需要验证迁移函数的逐版本、可回滚设计在真实场景下是否足够，必要时修订本 ADR 或另立后续 ADR。
- 若窗口布局状态的读写频率或复杂度显著增长（例如需要支持多窗口/多 profile），需要重新评估"独立 JSON 文件"是否仍是合适的存储形态。

## 关联

REQ-009、AC-002、WI-000、WI-015、EVD-LOOP-004。
