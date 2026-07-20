# 股市锦囊

一个 Windows 桌面小工具，界面用 PySide6，其余全部基于 Python 标准库。打包为一个免安装的应用目录（`股市锦囊/股市锦囊.exe`），解压后双击即用。它提供两种能力：

- **个股分析**：输入一个或多个 A 股代码，基于实时行情 + 历史日线，用可解释的多因子模型给出当日「买入/持有/卖出」倾向、理由、风险与保守投入参考。
- **全市场选股**：选择策略预设（强势动量、放量突破、超跌反弹、低估值蓝筹、高换手活跃、稳健低波动），微调关键参数，从**当前全市场实时行情**中按证券特征自动挑选股票，并对入选股做与个股分析一致的深度判断。

贯穿两页的核心是**五档决策强度**（稳健 · 稳进 · 标准 · 积极 · 激进）：客观测量不变，只调整决策策略——越激进越早出手、仓位越大、对风险越宽容；越稳健越要求强确认、仓位越小、更快减仓。点选档位即时重算、不重新联网。并配有三个实用模块：**决策强度光谱**（同一只股票五档结论一眼对照）、**仓位/风控计算器**（按风险预算 + ATR 止损给出股数/止损/止盈/最大亏损）、**可信度回测**（同股历史信号事后复盘）。配色采用 A 股本土习惯：红=涨/买，绿=跌/卖。

工作台能力：**自选股 / 持仓**（可填持仓成本与股数，看浮动盈亏）与本金、档位、预设、预警跨会话**持久化**（存到 `%APPDATA%\股市锦囊\config.json`，启动恢复）；**横向对比**把已分析的股票放进一张表（指标 + 各档强度提示 + 持仓盈亏）；K 线支持 **hover 十字光标**显示当根 OHLC；**条件预警**在开市挂机时，价格/涨跌幅/综合分越线即横幅 + 提示音提醒（边沿触发，仅程序开启时生效）；**个股资金流**按需查询主力净流入（今日 + 近5日，按需取数、降级安全，数据源不稳定时提示稍后重试，不影响其它功能）。

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

ADR-0001 接受的 Tkinter → PySide6 Widgets 迁移已经完成（WI-023）：`python main.py` 和 `股市锦囊.exe` 跑的都是 PySide6 版（`src/stock_advisor/qt_app/`），Tkinter 生产层已经删除，`ui/app.py` 只剩一个把 `run_gui` 委托给 Qt 装配的薄入口。

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
python -m pip install -r requirements-build.txt   # 唯一的构建期依赖 PyInstaller
python build_exe.py
```

构建中间产物全部放在 `build/`；最终交付物输出到 `dist/`：

- `dist/股市锦囊/` —— 应用目录，双击其中的 `股市锦囊.exe` 即可运行，无需安装。
- `dist/使用说明.html` —— 随构建生成的图文说明书。

采用 onedir 而非单文件是 ADR-0004 的决定，有两条独立理由：onefile 每次启动都要重新解压约 100 MB 运行时（实测热启动 2.9s，超出 2.5s 预算），而 onedir 是 0.69s；且 Qt 以 LGPL-3.0 分发，其第 4(d) 条要求用户能用自己的 Qt 重新链接——Qt DLL 作为独立文件放在应用目录里才做得到，压进单文件就做不到。

构建完成后可执行 `dist\股市锦囊\股市锦囊.exe --self-test` 验证打包程序能启动并跑通核心逻辑。

## 目录结构

```
run.bat / run.sh            一键启动脚本（CLI）
build.bat / build.sh        一键打包脚本（输出到 dist/）
main.py                     程序入口（GUI / --self-test）
build_exe.py                PyInstaller 打包脚本（中间产物 build/，交付物 dist/）
src/stock_advisor/
  domain/                   纯逻辑核心（无网络、无 GUI）
    models.py                 数据结构（行情、K线、指标、快照、测量、决策、仓位、回测）
    symbols.py                代码规范化与市场号映射
    engine.py                 客观测量层 measure()（多因子评分），analyze_stock 薄包装
    policy.py                 决策层：5 档决策强度、decide/仓位/光谱（纯逻辑）
    backtest.py               可信度回测：同股历史信号事后复盘（纯逻辑）
    chart.py                  K 线几何映射与 hover 命中（纯函数）
    compare.py                多股横向对比行组装（纯逻辑）
    alerts.py                 条件预警规则与边沿触发判定（纯逻辑）
    screener.py               选股过滤与排序（纯逻辑）
    presets.py                策略预设与可微调参数
  data/                     行情与样例数据获取
    data_provider.py          实时行情、历史日线、全市场快照获取（多源容错）
  services/                 编排与持久化
    workflow.py               个股分析与全市场选股编排（回传测量供改档重判）
    store.py                  用户配置持久化（自选股/持仓、本金、档位、预设、预警）
  ui/                       与界面框架无关的展示层
    app.py                    薄入口：run_gui 委托给 qt_app 装配
    theme.py                  token 单一真源（颜色/尺寸/字体/免责声明）——Qt 主题由此翻译成 QSS
    view_format.py            结果行/剪贴板/CSV 格式化（导出注入中和 + 免责声明页脚）
    manual.py                 使用说明 HTML 生成
    assets.py                 打包/仓库两态的资源路径解析（图标、tokens.json）
  qt_app/                   PySide6 界面（出货）
    app.py                    装配：4 个控制器 + 4 个功能页挂上 QTabWidget
    main_window.py            QMainWindow 外壳（标题栏身份、免责声明常驻、页面挂载）
    controllers/              异步控制器（QThreadPool + 队列信号，代次守卫丢弃迟到结果）
    pages/                    个股分析 / 全市场选股 / 条件预警 / 资金流四个功能页
    theme/fonts.py            字体契约：QFontInfo 如实报告实际字体，禁止静默回退（REQ-016/033）
  observability/            结构化日志（NDJSON；只写声明过的字段，原始报文不入日志）
tests/                      单元测试
docs/                       设计说明与实现计划
```

## 数据来源

实时行情、历史日线与全市场快照来自东方财富等公开行情接口，并带新浪、腾讯等备用源容错。无任何账号或密钥要求；接口临时不可用时程序会明确报错而不会伪造结果。
