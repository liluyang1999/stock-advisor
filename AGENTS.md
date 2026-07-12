# AGENTS.md — 股市锦囊 项目约定

面向在本仓库工作的编码代理与协作者。这里只写本项目特有、且无法从代码直接读出的约束与约定。

## 硬性约束

- **运行期只用 Python 标准库**：`tkinter`、`urllib`、`json`、`csv`、`threading` 等。任何运行期第三方依赖都不允许（会破坏单文件 EXE 的「放哪都能跑」目标）。
- **构建期唯一依赖是 PyInstaller**，通过 `pip install pyinstaller` 安装；见 `requirements-build.txt`。
- **不引入** Node、.NET、Electron、浏览器框架或其他非 Python 工具链。
- **交付物只有一个单文件 EXE**：`股市锦囊.exe`（onefile、windowed），随构建附带一份 HTML 说明书。
- **构建目录约定**：`build/` 只放构建中间产物（含 PyInstaller 原始产物）；`dist/` 只放最终交付物（EXE + HTML 报告）。不要使用 `outputs/`。
- **写边界**：构建只写项目内 `build/` 与 `dist/`，绝不写到项目目录之外。

## 架构与边界

核心逻辑与界面严格分离，便于测试与打包：

- `models.py` 只放数据结构（全部 `@dataclass(frozen=True)`）。
- `symbols.py` / `screener.py` / `presets.py` / `engine.py` / `policy.py` / `backtest.py` / `chart.py` / `compare.py` / `alerts.py` 是**纯逻辑、无网络、无 tkinter**，必须可独立单测。`store.py` 做配置读写（I/O），解析/序列化是纯函数。
- **条件预警**：`alerts.check_rules` 是**边沿触发纯函数**（条件假→真才触发，回落复位）；`app.py` 的监控环按 `MONITOR_INTERVAL_MS` 用线程跑 `analyze_symbol`，经队列回主线程判定，仅程序开启且不忙时进行。
- **持久化写到 `%APPDATA%\股市锦囊\config.json`**（应用自身运行态：自选股/持仓、本金、档位、预设），非项目产物；读坏/不可写都回退默认且不崩溃。测试经环境变量 `STOCK_ADVISOR_CONFIG` 指向临时文件隔离，**严禁让测试写真实 %APPDATA%**。
- **测量与决策分离**：`engine.measure()` 产出客观 `Measurement`（与档位无关）；`policy.decide(m, level)` 按 5 档决策强度翻译为买/持/卖与仓位；`engine.analyze_stock(..., level)` 是二者的薄包装，默认 L3「标准」复现既有行为。改档只对缓存的 `Measurement` 重判，不重新联网。
- `data_provider.py` 是唯一做网络请求的模块；解析函数（`parse_*`）保持纯函数以便单测。
- `workflow.py` 负责编排（个股分析、全市场选股），通过 Protocol 接收 provider，便于用 FakeProvider 测试；回传 `Measurement` 供界面改档重判。
- `app.py` 只负责界面、线程调度与渲染；可测的几何/格式化逻辑（含 `chart.py` K线几何、`build_*` 文本）抽成模块级纯函数。
- 配色为 A 股本土习惯：红=涨/买/积极，绿=跌/卖/谨慎，集中为命名常量。

新增功能优先复用现有引擎与渲染组件，不要重复造轮子。

## UI 布局约定（硬性）

- 所有窗体在主窗口（主窗口相对屏幕）**居中**，四边留白**均匀**。
- 内容限制最大宽度（`MAX_CONTENT_WIDTH`）并水平居中，超宽屏两侧均匀留白，组件不得单边拉伸过长。
- 居中与内容带计算抽成纯函数（`compute_centered_geometry`、`compute_content_band`）并有单测；改布局时先改/加测试。

## 测试与验证

- 测试命令：`python -m unittest discover -s tests`，提交前必须全绿。
- 改动遵循 TDD：先写失败测试，再实现。纯逻辑必须单测；GUI 用 headless 测试覆盖关键布局与交互。
- 语法检查：`python -m compileall -q main.py build_exe.py src/stock_advisor`（compileall 递归进子包，与 loop 门禁一致）。
- 打包后自验：`dist\股市锦囊.exe --self-test` 应退出码 0 并打印 `SELF_TEST_OK`。

## 行情数据约定

- 全市场快照走东方财富 clist 接口，市场号取自字段 `f13`（1=沪，0=深/北），**不要靠代码前缀猜 secid**；北交所新代码段为 `920xxx`。
- **资金流**走 `stock/fflow/kline/get`（个股主力净流入日线）；该接口偶发被限流/拒连（clist 的资金流字段则被直接拒），故仅做**按需、降级安全**的独立查询，绝不进核心分析流程；`parse_fund_flow_payload` 是纯函数可测，取不到时 UI 提示稍后重试。
- 字段可能缺失（`"-"`）或为负（如亏损股 PE），解析需鲁棒：缺失记 `None`，区间过滤遇缺失值在设了边界时判不通过。
- 接口失败必须明确报错，**绝不伪造行情或建议**。

## 立场

本产品是**可解释的辅助判断工具，不构成投资建议**。任何文案、模型输出都要保留这一边界，不得暗示确定性收益或「绝对预测」。
