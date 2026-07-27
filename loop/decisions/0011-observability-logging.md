# ADR-0011：可观测性与日志方案——标准库 logging + sink/轮转/error_class

- 状态：accepted
- 日期：2026-07-13

## 背景

REQ-023 要求所有结果携带数据来源、获取时间、完整度、新鲜度和降级状态；这类状态既要在 UI 呈现，也需要落盘可诊断。`architecture/OBSERVABILITY.md`（Task 1 产出）已经把日志 sink（stderr + `%APPDATA%\StockAdvisor\logs\` 下的 rotating file）、结构化 NDJSON 格式、字段集合、轮转策略（`RotatingFileHandler(maxBytes=5_242_880, backupCount=5)`）、日志级别阈值和 7 类 `error_class` 分类法都写清楚了，但这些都还只是架构规范文字，没有一份 ADR 把"这是不是本项目正式采用的可观测性方案"作为决策记录下来——尤其是"只用标准库 logging、不引入第三方结构化日志库"这一条本身就是一个需要被记录、可被重访的架构取舍，而不只是实现细节。

项目打包为无控制台窗口的 GUI EXE 后用户看不到 stderr（`OBSERVABILITY.md` 已指出这点），rotating file 因此是生产环境唯一对用户可诊断的持久 sink；这个"两个 sink 但只有一个在生产环境真正有效"的事实本身就是需要被显式决策并写入回滚/重访条件的架构约束。

## 决策

- 采用标准库 `logging`（含 `logging.handlers.RotatingFileHandler`）作为唯一日志实现，不引入第三方结构化日志库（例如 structlog、loguru）。
- 两个 sink：stderr（阈值 WARNING，交互式运行可见）+ `%APPDATA%\StockAdvisor\logs\stock_advisor.log` 的 rotating file（阈值 INFO，`maxBytes=5_242_880`、`backupCount=5`，尺寸驱动轮转），共享同一个自定义 `Formatter`，产出单行 NDJSON。
- 日志字段集合固定为：标准字段（`timestamp`/`level`/`logger`/`message`）+ 任务字段（`correlation_id`/`task_id`/`generation`/`operation`/`source`/`attempt`/`duration_ms`/`outcome`/`error_class`/`degraded`/`cancelled`）；禁止记录原始敏感 payload、完整自选/持仓或凭据。
- `error_class` 固定为 7 类互斥枚举（`network`/`parse`/`validation`/`persistence`/`gui`/`packaging`/`unknown`），作为 `architecture/NETWORK_RESILIENCE.md` 和 `architecture/DATA_QUALITY.md` 引用的唯一权威分类来源；`degraded`/`cancelled` 是独立于 `error_class` 的正交布尔字段。

## 替代方案

1. **第三方结构化日志库（structlog/loguru，拒绝）**：能提供更丰富的上下文绑定和更少样板代码，但引入一个新的运行时依赖（需要精确锁定版本和许可证审查，呼应 REQ-029），而项目运行时依赖已经因 PySide6/PyInstaller 迁移而显著增重（ADR-0001 的负面后果之一）；标准库 `logging` 配合一个自定义 `Formatter` 已经足以满足"单行 NDJSON、固定字段集合、两个 sink 共享同一格式"的全部需求，没有第三方库无法弥补的能力缺口。
2. **只用 stderr、不落盘（拒绝）**：GUI EXE 打包为无控制台窗口后用户完全看不到 stderr，一旦出问题用户除了口头描述现象外没有任何可以提供给开发者的诊断材料，与 REQ-023 要求结果携带可事后查证的完整度/新鲜度/降级状态相悖。
3. **时间驱动轮转，例如按天切分（拒绝）**：低频使用场景下会产生大量几乎为空的日志文件，对个人桌面工具而言没有实际诊断价值；尺寸驱动轮转（`maxBytes`）能保证轮转只在真正积累了足够诊断内容时发生。
4. **（采用）标准库 logging + 双 sink（stderr + rotating file）+ NDJSON + 尺寸驱动轮转 + 7 类 error_class**：见"决策"，具体数值和字段集合已由 `OBSERVABILITY.md` 规定，本 ADR 是该规范的正式决策记录。

## 后果

正面：

- 不新增运行时依赖：`logging`/`logging.handlers` 是标准库，不占用 REQ-029 的依赖锁定/许可证审查工作量，也不增加 EXE 体积或冷启动时间（呼应 RISK-002 对 onefile 包体/冷启动的关注）。
- 两个 sink 共享同一 `Formatter`，保证"开发环境用 stderr 看到的内容"与"生产环境用户可能提供的日志文件内容"完全一致，排查用户问题时不需要区分字段是否只在某个 sink 上才有。
- 固定的 7 类 `error_class` 枚举给 `NETWORK_RESILIENCE.md`/`DATA_QUALITY.md` 提供了单一权威分类来源，避免不同文档/模块各自发明差异措辞的错误分类。

负面/成本：

- 相比第三方结构化日志库，标准库方案需要自己维护一个自定义 `Formatter` 来保证 NDJSON 格式和字段集合一致，任何字段集合的变更都需要同步改这一个 `Formatter`，这是本 ADR 显式接受的"少依赖、多自己维护一点样板代码"的取舍。
- rotating file 总占用上限约 30 MiB（5 MiB × 6 个文件），在磁盘空间极度受限的目标机上仍占用一定空间；轮转策略已经设了上限，进一步降低上限是未来可调的策略数值，不是本 ADR 需要现在解决的问题。
- 本 ADR 记录的是目标方案；截至本次治理，产品代码尚未接入这套 logging 配置（`OBSERVABILITY.md` 描述的是架构规范而非已验证的实现），实际接入、`Formatter`/`error_class` 枚举的落地和相关测试属于具体工作项（例如 WI-020）的执行内容，不在本 ADR 范围。

## 回滚

若标准库 `logging` + 自定义 `Formatter` 方案在实现中被证明维护成本过高（例如字段集合频繁变化导致 `Formatter` 反复返工，或性能不满足 `OBSERVABILITY.md`"指标"一节的延迟预算），回滚路径是引入一个成熟的第三方结构化日志库替换 `Formatter` 层，但 sink 拓扑（stderr + rotating file）、字段集合契约和 `error_class` 分类法保持不变，回滚只影响"用什么生成这些字段"，不影响下游读日志的运维习惯或 `NETWORK_RESILIENCE.md`/`DATA_QUALITY.md` 对 `error_class` 的引用。停止条件：若日志写入本身（而非日志内容）被发现拖慢核心分析任务或阻塞 GUI 线程，必须立即把日志调用移出关键路径或改为异步/缓冲写入，不得为了保留同步日志调用而接受 GUI 卡顿。

## 重访触发

- 若未来需要跨进程/跨机器聚合日志（当前是单机桌面工具，不适用），需要重新评估是否引入更专业的日志基础设施。
- 若 `error_class` 分类法出现无法归类的真实场景（`OBSERVABILITY.md` 已把 `unknown` 定义为"理论上不应被正常路径触发；出现即视为分类体系本身需要修订的信号"），需要重新评审 7 类枚举是否需要扩展。
- WI-020（结构化日志与网络故障矩阵）执行落地时，若实测的日志写入延迟或轮转行为与本 ADR/`OBSERVABILITY.md` 描述不符，需要重新评审具体数值。

## 关联

REQ-023、WI-000、WI-020、EVD-LOOP-004。
