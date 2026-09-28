# AGENTS.md — 股市锦囊 项目约定

面向在本仓库工作的编码代理与协作者。这里只写本项目特有、且无法从代码直接读出的约束与约定。

## 硬性约束

- **GUI 栈就是 PySide6。** ADR-0001 的 Tkinter→PySide6 Widgets 迁移（REQ-011/012/013）已由 **WI-023 完成**：`main.py` → `ui/app.run_gui` → `qt_app.app.run_qt_gui`，Tkinter 生产层（10 个文件）已删除，生产源零 `tkinter` import 由 TEST-ARCH-002 的 AST 全量扫描机器强制。新界面代码一律写在 `src/qt_app/`；`ui/` 保留共享展示逻辑和薄入口，设计 token 真源是 `loop/product/tokens.json`。
- **运行期依赖只有 PySide6-Essentials**，它在 `pyproject.toml` 的 `[project].dependencies` 里（WI-025 随出货一并移入）。除它以外一律只用标准库（`urllib`、`json`、`csv`、`decimal`、`threading`）。**新增其它运行期第三方依赖仍然不允许**——每加一个都要重做许可证、SBOM 与打包体积的论证。
  - 领域内核（`domain/` 12 个模块）连 PySide6 和 `urllib` 都不许 import，由 G-CORE 门禁静态强制。Qt 是应用的依赖，不是模型的依赖。
- **构建期唯一依赖是 PyInstaller**，精确钉在 `pyproject.toml` 的 `[dependency-groups].build` 里（与 dev/gui 同一机制），装法 `python -m pip install --group build`。构建依赖必须钉死版本：交付物可复现性取决于它。
- **不引入** Node、.NET、Electron、浏览器框架或其他非 Python 工具链。
- **交付物是一个应用目录**：`dist/股市锦囊/`（onedir、windowed，内含 `股市锦囊.exe` 与 Qt 运行时），随构建附带一份 HTML 说明书 `dist/使用说明.html`。
  - **ADR-0004 已 accepted：onedir，不是 onefile**，两条独立理由：onefile 热启动 2.903 s 超出 `warm_start_seconds` 2.5 s 预算（每次启动重解压约 100 MB），onedir 0.685 s；且 PySide6 的 **LGPL-3.0** 第 4(d) 条重链接义务只有 onedir 履行得了（Qt DLL 是可替换的独立文件）。不要改回 onefile。
- **构建目录约定**：`build/` 只放构建中间产物（含 PyInstaller 原始产物）；`dist/` 只放最终交付物（EXE + HTML 报告）。不要使用 `outputs/`。
- **写边界**：构建只写项目内 `build/` 与 `dist/`，绝不写到项目目录之外。

## 架构与边界

核心逻辑与界面严格分离，便于测试与打包：

- `models.py` 只放数据结构（全部 `@dataclass(frozen=True)`）。
- `symbols.py` / `screener.py` / `presets.py` / `engine.py` / `policy.py` / `backtest.py` / `chart.py` / `compare.py` / `alerts.py` 是**纯逻辑、无网络、无 GUI**（G-CORE 静态禁止 `urllib` 与 `PySide6`），必须可独立单测。`store.py` 做配置读写（I/O），解析/序列化是纯函数。
- **条件预警**：`alerts.check_rules` 是**边沿触发纯函数**（条件假→真才触发，回落复位）；周期监控由 `qt_app/controllers/alert_controller.py` 的 `QTimer` 驱动（默认 60000 ms，见 `AlertController.start`），每轮在 worker 线程跑、结果经队列信号回 GUI 线程判定，仅程序开启时生效。
- **持久化写到 `%APPDATA%\StockAdvisor\config.json`**（应用自身运行态：自选股/持仓、本金、档位、预设），非项目产物；读坏/不可写都回退默认且不崩溃。测试经环境变量 `STOCK_ADVISOR_CONFIG` 指向临时文件隔离，**严禁让测试写真实 %APPDATA%**。
- **测量与决策分离**：`engine.measure()` 产出客观 `Measurement`（与档位无关）；`policy.decide(m, level)` 按 5 档决策强度翻译为买/持/卖与仓位；`engine.analyze_stock(..., level)` 是二者的薄包装，默认 L3「标准」复现既有行为。改档只对缓存的 `Measurement` 重判，不重新联网。
- 网络接入只在 `data/`：`data_provider.py` 保留解析与兼容 provider，生产由 `bounded_adapter.py` 配合 `bounded_transport.py` 提供有界请求；解析函数（`parse_*`）保持纯函数以便单测。
- `workflow.py` 负责编排（个股分析、全市场选股），通过 Protocol 接收 provider，便于用 FakeProvider 测试；回传 `Measurement` 供界面改档重判。
- 界面层只负责呈现与编排：`qt_app/pages/` 是薄视图，异步与取消在 `qt_app/controllers/`，业务判断一律留在 `domain`/`services`。可测的几何/格式化逻辑（`chart.py` K 线几何、`ui/view_format.py` 格式化）都是模块级纯函数。
- 配色为 A 股本土习惯：红=涨/买/积极，绿=跌/卖/谨慎。**色值真源是 `loop/product/tokens.json`**（带 WCAG 对比度实测），Qt 侧经 `qt_app/theme/tokens.py` 读取生成 QSS；`ui/theme.py` 只留少数非 Qt 路径（说明书 HTML、纯函数格式化）仍在用的色值，新增颜色一律加进 tokens.json。

新增功能优先复用现有引擎与渲染组件，不要重复造轮子。

## UI 布局约定（硬性）

- 所有窗体在主窗口（主窗口相对屏幕）**居中**，四边留白**均匀**。
- 内容限制最大宽度（`MAX_CONTENT_WIDTH`）并水平居中，超宽屏两侧均匀留白，组件不得单边拉伸过长。
- 窗口居中交给 Qt 原生（Tk 时代的 `ui/layout.py` 几何纯函数已随 Tk 生产层移除）；内容最大宽度在 `qt_app/main_window.py` 以 `theme.MAX_CONTENT_WIDTH` / `CONTENT_MARGIN` 施加，改这些常量或布局时先改/加测试。

## 测试与验证

- 测试命令：`python -m unittest discover -s tests`，提交前必须全绿。
- 改动遵循 TDD：先写失败测试，再实现。纯逻辑必须单测；GUI 用 headless 测试覆盖关键布局与交互。
- 语法检查：`python -m compileall -q main.py scripts src`（compileall 递归进子包，与 loop 门禁一致）。
- 打包后自验：`dist\股市锦囊\股市锦囊.exe --self-test` 应退出码 0 并打印 `SELF_TEST_OK`。

## 行情数据约定

- 全市场快照走东方财富 clist 接口，市场号取自字段 `f13`（1=沪，0=深/北），**不要靠代码前缀猜 secid**；北交所新代码段为 `920xxx`。
- **资金流**走 `stock/fflow/kline/get`（个股主力净流入日线）；该接口偶发被限流/拒连（clist 的资金流字段则被直接拒），故仅做**按需、降级安全**的独立查询，绝不进核心分析流程；`parse_fund_flow_payload` 是纯函数可测，取不到时 UI 提示稍后重试。
- 字段可能缺失（`"-"`）或为负（如亏损股 PE），解析需鲁棒：缺失记 `None`，区间过滤遇缺失值在设了边界时判不通过。
- 接口失败必须明确报错，**绝不伪造行情或建议**。

## 立场

本产品是**可解释的辅助判断工具，不构成投资建议**。任何文案、模型输出都要保留这一边界，不得暗示确定性收益或「绝对预测」。
