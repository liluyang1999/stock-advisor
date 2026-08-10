# 股市锦囊

一个 Windows 桌面小工具，界面用 PySide6，其余全部基于 Python 标准库。打包为一个免安装的应用目录（`股市锦囊/股市锦囊.exe`），解压后双击即用。它提供两种能力：

- **个股分析**：输入一个或多个 A 股代码，基于实时行情 + 历史日线，用可解释的多因子模型给出当日「买入/持有/卖出」倾向、理由、风险与保守投入参考。
- **全市场选股**：选择策略预设（强势动量、放量突破、超跌反弹、低估值蓝筹、高换手活跃、稳健低波动），微调关键参数，从**当前全市场实时行情**中按证券特征自动挑选股票，并对入选股做与个股分析一致的深度判断。

贯穿两页的核心是**五档决策强度**（稳健 · 稳进 · 标准 · 积极 · 激进）：客观测量不变，只调整决策策略——越激进越早出手、仓位越大、对风险越宽容；越稳健越要求强确认、仓位越小、更快减仓。点选档位即时重算、不重新联网。并配有三个实用模块：**决策强度光谱**（同一只股票五档结论一眼对照）、**仓位/风控计算器**（按风险预算 + ATR 止损给出股数/止损/止盈/最大亏损）、**可信度回测**（同股历史信号事后复盘）。配色采用 A 股本土习惯：红=涨/买，绿=跌/卖。

工作台能力：**自选股 / 持仓**（可填持仓成本与股数，看浮动盈亏）与本金、档位、预设、预警跨会话**持久化**（存到 `%APPDATA%\StockAdvisor\config.json`，启动恢复）；**横向对比**把已分析的股票放进一张表（指标 + 各档强度提示 + 持仓盈亏）；K 线支持 **hover 十字光标**显示当根 OHLC；**条件预警**在开市挂机时，价格/涨跌幅/综合分越线即横幅 + 提示音提醒（边沿触发，仅程序开启时生效）；**个股资金流**按需查询主力净流入（今日 + 近5日，按需取数、降级安全，数据源不稳定时提示稍后重试，不影响其它功能）。

> 模型结果仅供研究和辅助决策，**不构成任何投资建议**；交易前请自行核验行情、公告与风险。

## 运行

直接用脚本启动（推荐，CLI 一行即可）：

```bash
run.bat              # Windows（cmd / PowerShell）
./run.sh             # Git Bash / WSL
run.bat --self-test  # 透传参数：离线自测（不触网）
```

或手动调用：

```bash
python main.py            # 启动图形界面
python main.py --self-test  # 离线自测：验证个股分析与选股管线（不触网）
```

要求 Python 3.14+。运行期依赖只有一个：PySide6-Essentials（图形界面）。其余全部是标准库（`urllib`、`json`、`csv`、`decimal` 等）。从源码运行前先装：

```bash
python -m pip install --group gui   # PySide6-Essentials（运行期）+ pytest-qt（仅测试期）
```

拿到打包好的 `股市锦囊.exe` 的用户不需要装任何东西——Qt 运行时已随应用目录分发。

### GUI 栈：PySide6

ADR-0001 接受的 Tkinter → PySide6 Widgets 迁移已经完成（WI-023）：`python main.py` 和 `股市锦囊.exe` 跑的都是 PySide6 版（`src/qt_app/`），Tkinter 生产层已经删除，`ui/app.py` 只剩一个把 `run_gui` 委托给 Qt 装配的薄入口。

领域内核（`domain/` 的 12 个模块）与 Qt 无关，这一点由 G-CORE 门禁静态强制：内核里不允许出现 `PySide6` 或 `urllib` 的 import。换界面框架不需要动内核。

## 测试

```bash
python -m unittest discover -s tests
```

纯逻辑（代码解析、行情解析、指标、筛选、排序、预设、编排、布局计算）均有单元测试覆盖；GUI 关键布局与交互也有 headless 测试。

## 构建 Windows 交付物

直接用脚本打包（会自动安装唯一的构建依赖 PyInstaller）：

```bash
build.bat            # Windows（cmd / PowerShell）
./build.sh           # Git Bash / WSL
```

或手动执行：

```bash
python -m pip install --group build   # 唯一的构建期依赖 PyInstaller（版本已钉）
python scripts/build_exe.py
```

构建中间产物全部放在 `build/`；最终交付物输出到 `dist/`：

- `dist/股市锦囊/` —— 应用目录，双击其中的 `股市锦囊.exe` 即可运行，无需安装。
- `dist/使用说明.html` —— 随构建生成的图文说明书。

采用 onedir 而非单文件是 ADR-0004 的决定，有两条独立理由：onefile 每次启动都要重新解压约 100 MB 运行时（实测热启动 2.9s，超出 2.5s 预算），而 onedir 是 0.69s；且 Qt 以 LGPL-3.0 分发，其第 4(d) 条要求用户能用自己的 Qt 重新链接——Qt DLL 作为独立文件放在应用目录里才做得到，压进单文件就做不到。

构建完成后可执行 `dist\股市锦囊\股市锦囊.exe --self-test` 验证打包程序能启动并跑通核心逻辑。

## 目录结构

仓库分四类：**产品代码**、**验证**、**治理控制平面**、**入口与交付**。前三类互不越界，第四类把它们串起来。

### 一、产品代码 `src/`

各架构层直接是 `src/` 下的顶级包（ADR-0007 的四分层保留；ADR-0015 移除了原 `stock_advisor/`
包根，导入随之从 `stock_advisor.domain.engine` 缩短为 `domain.engine`）。箭头是**允许的依赖
方向**，反向依赖会被门禁拒绝：

```
qt_app/ ──> ui/ ──> services/ ──> data/ ──> domain/
                                    observability/（横切，各层皆可用）
```

`domain/` 的纯度不是靠自觉，是**机器强制**的：`loop/scripts/check_core_boundaries.py`
静态分析 12 个受保护核心模块的 import，越界即红（G-CORE 门禁；扫平后层名列入禁入根，
机制经变异验证——人为注入越层导入会立即变红）。

```
src/
  version.py                产品版本单一真源（原 stock_advisor/__init__.py）
  ports.py                  网络传输的 port/envelope 合同（框架无关、纯 stdlib，两代传输共用）
  domain/                   纯逻辑核心 · 16 模块 · 无网络、无 GUI、无磁盘
    models.py                 数据结构（行情、K线、指标、快照、测量、决策、仓位、回测）
    money.py / numeric.py     金额与价格的 Decimal 表示（ADR-0013）；浮点解析的唯一入口
    symbols.py                代码规范化与市场号映射
    engine.py                 客观测量层 measure()（多因子评分），analyze_stock 薄包装
    policy.py                 决策层：5 档决策强度、decide/仓位/光谱
    backtest.py               可信度回测：同股历史信号事后复盘
    screener.py / presets.py  选股过滤排序 · 策略预设与可微调参数
    chart.py                  K 线几何映射与 hover 命中（纯函数，供 QPainter 绘制）
    compare.py / alerts.py    多股横向对比行组装 · 条件预警规则与边沿触发判定
    formatting.py             数值/单位的呈现规则
    input_validate.py         外部输入的边界校验
    data_quality.py           行情数据的可信度判定
  data/                     外部接入 · 4 模块
    data_provider.py          实时行情、历史日线、全市场快照获取（多源容错）
    bounded_transport.py      有界 HTTP 传输（超时/大小上限，防挂死与超大响应）
    sample_data.py            离线样例数据
  services/                 用例编排与持久化 · 9 模块
    workflow.py               个股分析与全市场选股编排（回传测量供改档重判）
    store.py                  用户配置持久化（自选股/持仓、本金、档位、预设、预警）
    screener_run.py           选股批次执行 · batch.py 批处理调度
    alert_monitor.py          预警轮询与触发 · tier_switch.py 档位切换
    fund_flow.py              个股资金流取数编排
    self_check.py             端到端自检（main.py --self-test 的实现）
  observability/            结构化日志（NDJSON；只写声明过的字段，原始报文不入日志）
  ui/                       与 GUI 框架无关的展示逻辑 · 7 模块
    view_text.py              文案与结果文本组装
    view_format.py            结果行/剪贴板/CSV 格式化（导出注入中和 + 免责声明页脚）
    theme.py                  应用身份/窗口尺寸/表列与排序序/免责声明
    manual.py                 使用说明 HTML 生成
    assets.py                 打包/仓库两态的资源路径解析（图标、tokens.json）
    app.py                    薄入口：run_gui() 委托给 qt_app 装配，保持入口契约不变
  qt_app/                   PySide6 界面（出货）· 36 模块
    app.py                    装配：4 类控制器 + 5 个功能页挂上 QTabWidget
    main_window.py            QMainWindow 外壳（标题栏身份、免责声明常驻、页面挂载）
    settings.py               五项持久化设置的单一归属（WI-030）
    pages/                    个股分析 / 全市场选股 / 自选持仓 / 条件预警 / 个股资金流
    controllers/              异步控制器（QThreadPool + 队列信号，代次守卫丢弃迟到结果）
    workers/                  后台任务体 · table_models/ QAbstractTableModel + 排序代理
    widgets/                  自绘控件（K线、因子条、光谱条、卡片、预设网格…）
    dialogs/                  模态对话框
    theme/                    QSS 与设计令牌；fonts.py 字体契约：QFontInfo 如实报告实际
                              字体，禁止静默回退（REQ-016/033）。色值真源是 loop/product/tokens.json
```

### 二、验证 `tests/`

```
tests/
  test_*.py                 73 个测试文件（27 个 test_qt_* 界面测试 + 46 个逻辑测试）
  fixtures/                 测试数据：golden_indicators.json（人手笔算的黄金样本，
                            绝不由被测代码生成，否则是循环验证）
  performance/              性能基准（bench_util.py + test_performance.py）
  qt_test_helpers.py        Qt 测试公共夹具
```

界面测试在 `QT_QPA_PLATFORM=offscreen` 下跑真实 QWidget，无需显示器。

### 三、治理控制平面 `loop/`

与产品代码**平行且互不导入**的一套工程治理数据。它是本仓库需求→决策→实现→证据链条的真源：

```
loop/
  decisions/                ADR 决策记录（架构选型及其权衡与回滚条件）
  architecture/             目标架构、模块边界、核心模块清单、计算规格
  planning/                 工作项与依赖图 · registers/ 需求与风险登记册
  quality/                  质量门定义、追溯矩阵、测试目录、工具链基线
  product/                  产品面：设计令牌、能力面、UI 设计系统
  state/                    当前状态、待办、指标、证据索引、进度日志（追加型）
  evidence/                 门禁运行、基线、发布的证据留档
  governance/               版本与变更控制规程 · baseline/ 仓库与依赖基线
  scripts/                  校验器与门禁运行器（validate_loop / run_gates /
                            check_core_boundaries / check_traceability / check_coverage …）
  schemas/ templates/       上述 JSON 的 schema 与模板 · tests/ 控制平面自身的测试
```

### 四、入口、构建与交付

```
main.py                     程序入口（GUI / --self-test）
scripts/                    工具脚本（不随应用分发）
  build_exe.py                PyInstaller 打包（中间产物 build/，交付物 dist/）
  make_release_manifest.py    发布清单、第三方声明、SBOM 生成
  capture_ui.py               逐页截图供视觉评审：python scripts/capture_ui.py
                              [--states success fail empty]（自带假数据，不联网、不碰用户配置）
run.bat / run.sh            一键启动 · build.bat / build.sh 一键打包
pyproject.toml              项目元数据 + ruff/pyright/pytest/coverage 配置的唯一归属
.pre-commit-config.yaml     提交前钩子（ruff format / ruff check / validate_loop）
.github/workflows/ci.yml    CI（windows-latest，门禁全量强制）
assets/ licenses/           应用图标 · Qt 的 LGPL/GPL 许可证文本（随交付物分发）
knowledge/                  知识库：本项目全部知识点的图文教学材料（knowledge/index.html 是入口）
docs/                       过程性记录：设计规格、实施计划、界面概念稿（docs/README.md 是索引）
```

> **两条命名与布局的既有说明**
>
> - `src/` 下**不再有** `stock_advisor/` 包根（ADR-0015）：各层直接是顶级包，导入形如
>   `domain.engine` / `qt_app.app`。代价是 `domain`/`data`/`services`/`ui` 成为本项目占用的
>   顶级模块名——本应用离线运行、依赖封闭钉版（仅 PySide6-Essentials），且 `src/` 在
>   sys.path 首位，故风险有界；但**新增运行期依赖前须确认不与这些名字冲突**。G-CORE 门禁
>   已随之适配：层名列入 `forbidden_import_roots`，越层导入（如今必然是绝对形式）照样即红，
>   机制经变异验证。产品在日志里的命名空间仍叫 `stock_advisor`（`observability/log.py`），
>   那是产品身份，与目录无关。
> - `ui/` 这个名字是 Tkinter 时代的遗产。WI-023 迁移完成后它已不含任何 Tk 代码，职责变成
>   "与 GUI 框架无关的展示逻辑"，与 `qt_app/` 并列而非上下层。ADR-0007 的"重访触发"已登记
>   此事，改名需另立 ADR。

## 数据来源

实时行情、历史日线与全市场快照来自东方财富等公开行情接口，并带新浪、腾讯等备用源容错。无任何账号或密钥要求；接口临时不可用时程序会明确报错而不会伪造结果。
