# 股市锦囊 — 界面整改 + 查缺补漏 设计

> 在既有功能全绿(390 单测通过)的基础上,**根治高 DPI 下窗口不居中/尺寸错乱的运行期 bug、把很深的单列堆叠重构为紧凑分区并统一视觉、补齐用户可见的功能瑕疵、拆分 4056 行的 `app.py`、清理首次提交的 git 卫生**。交付物仍为单文件 EXE `dist/股市锦囊.exe`。运行期只用 Python 标准库,构建期只依赖 PyInstaller。

## 目标

1. **窗口几何正确**:程序打开时窗口在**屏幕工作区正中央**,长宽随屏幕/DPI 自适应到"合适"尺寸,四边留白均匀(满足 `AGENTS.md` 硬约束)。
2. **界面赏心悦目、交互舒适**:重排信息架构、合并冗余面板、统一卡片/间距/字号,消除文字重叠/裁切/溢出。
3. **查缺补漏**:修复用户可见的功能瑕疵与文档漂移;不引入伪造行情/建议。
4. **代码健康**:`app.py` 回归 `AGENTS.md` 规定的"只负责界面/线程/渲染",纯逻辑抽为可独立单测的模块。
5. **交付卫生**:首次提交不夹带构建产物与二进制;构建脚本跨平台分隔符正确。
6. **全程可验证**:每一步 `python -m unittest discover -s tests` 全绿;关键运行期几何补真机回归测试。

## 约束(沿用既有)

- 运行期只依赖 Python 标准库(`tkinter/urllib/json/csv/threading` 等);构建期只允许 `pip install pyinstaller`。
- 不引入 Node/.NET/浏览器框架或非 Python 工具链。
- 交付物:`dist/股市锦囊.exe`(onefile/windowed)+ 一份 HTML 使用说明。
- 配色为 A 股本土习惯:**红=涨/买/积极,绿=跌/卖/谨慎**(全局统一)。
- 立场:可解释的辅助判断工具,**不构成投资建议**,不得暗示确定性收益。

## 用户已确认的范围决策

- **整改深度**:重构布局 + 修复 + 视觉统一(保留全部现有功能,不改核心逻辑;不做整套视觉语言重设计)。
- **查缺补漏范围**:用户可见的功能瑕疵/文档漂移 + 拆分 `app.py` + 打包/交付链路核对。
- **拆分深度**:纯函数模块 **+ 子窗口 Mixin**(自选/对比/预警窗口构建抽成 Mixin;监控环留 `app.py`)。
- **git 卫生**:`build/` 与 `dist/`(含 EXE 与 HTML 说明)**一并 gitignore**,靠 `build_exe.py` 按需重建;源码、`assets/` 图标、`docs/` 入库。
- **过时技术报告**:`docs/stock_advisor_technical_stack_report.html` **按现状重新生成**(新名、五档决策、完整模块清单、正确红绿配色)。

## 现状诊断(实据)

**A. 窗口几何 bug(已用探针脚本证实,4K@250% 机器)**

```
DPI 模式 = SetProcessDpiAwareness(1);winfo_screen = 3840×2160;tk scaling = 3.3366
SPI_GETWORKAREA = (0,0,3840,2040)  ← 物理工作区
scale_work_area_for_tk → 1536×816  ← 却被 ÷2.5 缩成"逻辑"单位
compute_centered_window → 1376×680 +72+48
最终窗口 = 物理屏幕的 36%×31%,缩在左上角
```

根因:`main.py` 的 `enable_dpi_awareness()` 让进程 DPI 感知 → **Tk 的 `geometry()` 单位变为物理像素**;`SystemParametersInfo(SPI_GETWORKAREA)` 也返回物理像素(与 geometry 同一坐标系)。但 `app.py:_screen_work_area` 里的 `scale_work_area_for_tk` 仍按旧假设把工作区 ÷2.5,算出的 1376×680 被 Tk 当物理像素画出 → 小窗 + 错位。字体按 pt 自动放大 2.5–3.3×,在过小窗口里溢出裁切。**390 个纯函数单测全过,恰因这段运行期耦合无人覆盖。**

**B. 渲染系统性根因**:字体全用 pt(随 tk scaling 放大 2.5–3.3×),而画布坐标、`height=300/48/32`、Treeview `rowheight=32`、K线 tooltip 框宽 `7.2×字数`、`wraplength` 等**全是固定像素**,二者错配是绝大多数瑕疵之源:
- `_draw_empty_visual`/`_draw_visual`:徽标框与两行标题用 96-DPI 固定坐标,行距仅 26px,而 250% 下行高 40–47px → "待分析/今日结论/等待分析结果"上下重叠、"待分析"横向溢出徽标框。
- `_draw_spectrum_strip`:`spectrum_canvas` 高 48px,两行文字 y=18/33(差 15px)→ 档名与买/卖标签重叠。
- Treeview `rowheight=32` 固定,10pt 文字放大后被纵向裁切。
- K线十字光标 tooltip 底框按 `7.2×字数` 估宽、固定高 20px → 文字溢出。
- 四个子窗口(自选 720×520、对比 1200×560、预警 780×560、说明 880×580)尺寸全固定,同源溢出风险;对比窗 11 列合计 ~1050px 固定,高 DPI 下横向溢出。

**C. 结构冗余**(未分析即渲染 ~600px 假占位):走势 sparkline 与 K 线两张价格图重复;洞察条 4 指标与 `_draw_visual` 徽标指标语义重复;光谱既画成条又塞进详情文字;状态/摘要/概览三段并列。

**D. 功能瑕疵**(详见 WS4):档位说明算了却从不显示、说明书"滑杆·拖动"实为分段按钮、选股参数上下限可交叉、免责声明两套措辞、资金流 worker 越线调 `after()`、预警字段下拉显英文键、技术报告 HTML 配色讲反。

**E. 已确认健壮(不动)**:网络失败显式报错不伪造;缺失值/负 PE/空结果各处有防护;线程经队列回主线程(除 WS4-M6);预警边沿触发正确;11 项功能均有接通 UI 入口。

---

## WS1 · 窗口几何 & DPI(根治不居中/尺寸错乱)

**模型**:保留 DPI 感知(渲染清晰),几何单位统一到 **Tk geometry 单位 == SPI_GETWORKAREA 单位**(DPI 感知时二者皆物理像素,同一坐标系,无需换算)。

- **移除** `scale_work_area_for_tk` 的反向缩小(它是把窗口缩成 1/3 的元凶);工作区测量值直接作为几何。
- 新增 UI 缩放因子 `ui_scale = max(1.0, tk_scaling * 72 / 96)`(250% → ≈2.5),把逻辑尺寸常量按它放大:`MAIN_MIN_SIZE`、`WINDOW_MAX_SIZE`、`WINDOW_WORKAREA_MARGIN`、`MAX_CONTENT_WIDTH`、`INFO_WINDOW_SIZE` 及各子窗口尺寸,统一经 `scale(px)=round(px*ui_scale)` 得到目标物理像素。
- 窗口 = `clamp(工作区 − 2×margin, min, max)`,按**外框**在工作区居中(沿用 `compute_centered_window` 的 frame 校正与两遍 `update_idletasks` 实体化)。四边留白均匀。
- 内容带 `compute_content_band` 用放大后的 `MAX_CONTENT_WIDTH`:常规窗口内容填满且左右均匀留白,超宽屏才居中收窄。
- 子窗口 `_center_child_window` 相对主窗口居中,尺寸经 `scale()`。
- **保留 `compute_centered_geometry/compute_window_position/normalize_work_area_to_screen/choose_centering_screen_size/compute_centered_window/compute_content_band` 等纯函数**(已有单测);仅调整调用侧的单位与常量,并删除 `scale_work_area_for_tk`(及其单测)。
- **降级**:`SetProcessDpiAwareness` 失败(极老 Windows)时进程为 DPI 非感知,此时 `winfo_screen`/`SPI_GETWORKAREA`/geometry 同为逻辑单位、仍自洽;`ui_scale` 退化为 1.0,几何模型不变。

**验证(补此前缺失的运行期覆盖)**:headless 测试构造 `Tk`,注入受控的 `tk_scaling` 与工作区,断言最终 `geometry()` 客户区落在 `[min, 工作区−2margin]`、四边留白差 ≤1px、窗口不越出工作区;并覆盖 250%/100% 两档。

## WS2 · DPI-稳健渲染(根治重叠/裁切/溢出)

统一以 `ui_scale` 驱动所有原本硬编码的像素量;文字块排布改为基于**字体度量**而非绝对坐标。

- 引入 `scale(px)` 助手(与 WS1 同一因子),套用到:画布高(`visual`/`kline_canvas` 300、`spectrum_canvas` 48)、绘制坐标偏移、Treeview `rowheight`、K线 tooltip 框宽高、进度条 `length/thickness`、滚动条 `width`、Spinbox `arrowsize`、各 `wraplength`。
- `_draw_empty_visual`/`_draw_visual`:徽标框尺寸与文字纵向间距改用 `font.metrics("linespace")` 度量逐行下推,横向按 `font.measure(text)` 定位,消除重叠与溢出;`action_label`(可"买入/加仓")过长时按测量截断或缩框。
- `_draw_spectrum_strip`:画布高与两行文字间距按度量计算;或改为单行紧凑呈现。
- Treeview `rowheight` 按字体 `linespace + 内边距` 计算。
- 纯几何/度量计算尽量抽成可单测的纯函数(输入字号/缩放 → 输出坐标),GUI 侧只做绘制。

## WS3 · 布局重构 & 视觉统一(紧凑分区)

保留全部功能,只重排与统一(结构见随本设计交付的线框对比)。

**信息架构(自上而下)**:页眉(紧凑)→ 控制条(模式 · 决策强度 · **档位说明**)→ 输入/操作区 → 状态+概览(合并一条)→ 结果表(有结果才展开)→ **结论卡**(方向/仓位/把握/波动 + 五档光谱)→ **价格卡**(单一 K 线 + 判断拆解因子)→ 详情卡(说明 + 本金计算器)→ 免责。

- **合并冗余**:走势 sparkline 与 K 线二选一(留 K 线);洞察条 4 指标 + 光谱尺并为一张结论卡;状态/摘要/概览三段并为一条;删除死变量 `visual_summary_var`(未绑定任何控件)。
- **折叠空态**:未分析时结论卡/价格卡/详情卡折叠为单行提示,消除 ~600px 假占位;有结果再展开。
- **统一视觉系统**:抽出单一卡片构件(统一圆角/描边色/内层底色,消除 `#ffffff`/`#fbfdff`/`#e9f1fc` 混用)、单一间距刻度(替换零散 pad 值)、单一字号层级。
- **子窗口公共构件**:自选/对比/预警三窗共用的"指标条 + Treeview 卡 + 底部按钮行"抽成复用构件,尺寸经 `scale()`;对比窗多列改为可横向滚动或按 DPI 收敛列宽。
- 纯函数(布局带宽、行/文本格式化)保持可单测;GUI 用 headless 测试覆盖关键结构(区块存在、折叠/展开切换、控制条含档位说明标签)。

## WS4 · 功能补漏(用户可见瑕疵)

| 级别 | 项 | 位置 | 修复方向 |
|---|---|---|---|
| 中 | 每档"决策强度说明"算了却从不显示(`level_label_var` 未绑定;`level_summary` 死用) | `app.py:158,997,2679` | 挂到控制条 Label(WS3 的"档位说明");与 UI 审计的死变量互印证 |
| 中 | 说明书/README 把分段按钮误称"滑杆·拖动" | `manual.py:89-91`、`README.md:8`(→重建 `dist/使用说明.html`) | 改为"分段按钮/点选档位" |
| 中 | 选股微调参数上下限可交叉 → 空结果 + 误导提示 | `presets.py:apply_tunables 148-166` | 对成对边界做 `min≤max` 协同校验,交叉时明确提示(区别于"放宽范围") |
| 中 | 免责声明两套措辞并存 | `app.py:93` vs `policy.py:28` | 收敛为单一权威常量,`policy` 复用 |
| 中 | 资金流 worker 从后台线程直接 `self.root.after()` | `app.py:1700-1708` | 改走队列 + 主线程轮询,与其余三个 worker 一致 |
| 低 | 预警"字段"下拉显英文键(price/change_pct/score) | `app.py:1490-1492` | 显示 `FIELD_LABELS` 中文标签,保存映射回键 |
| 低 | `measure` 与 `policy` 取整口径不一(截断 vs 四舍五入),破坏"L3=客观综合分"文档承诺 | `engine.py:199` vs `policy.py:96-97` | 统一取整方式 |
| 低 | 死导入/死常量(`board_of`/`default_values`/`ACTION_BUTTON_LABELS` 仅测试用) | `app.py:41-42,81` | 清理或明确保留说明 |
| — | ⚠️ 技术报告 HTML 把红绿买卖讲反、整篇过时 | `docs/stock_advisor_technical_stack_report.html` | **按现状重新生成**:新名"股市锦囊"、五档决策强度、每档仓位上限、完整模块清单、`dist/` 路径、正确 A 股配色;数据层回退链章节仍准确可留 |
| 低 | 旧 spec/plan 仍写 `outputs/` 与旧名 | `docs/superpowers/specs|plans/2026-06-2{1,2}-*` | 顶部加"已被本设计取代"指引(不改历史结论) |

不改核心决策模型(五档阈值/权重/预算/上限已与设计逐值吻合)。

## WS5 · 拆分 app.py(4056 行 → 回归界面/线程/渲染)

**依赖单向无环**;新模块一律不 `import app`。app.py 用 `from .x import 名字` **真名 re-export**,使 `tests/*` 现有 `from stock_advisor.app import X` 与类方法体裸名调用零改动、每步全绿。

| 新模块 | 职责 | 迁入(约行) |
|---|---|---|
| `theme.py` | UI 常量单一真源(颜色/尺寸/表列/排序序/免责/样例输入) | ~55 |
| `layout.py` | 居中/工作区/内容带几何 + `active_mode_action` | ~100 |
| `formatting.py` | 数值强制 + 低层格式化 + `risk_level` + 文本谓词 | ~185 |
| `view_text.py` | 面向用户的整块文本构建 + 文案改写(`build_*`/`_plain_text`/`_friendly_*`) | ~470 |
| `view_format.py` | 行/表/剪贴板格式化 + 行/详情标签配色 | ~200 |
| `sample_data.py` | 离线样例/空态占位数据(`make_sample_*`) | ~65 |
| `input_validate.py` | 输入解析与可调项校验(`is_partial_number`/`validate_tunable`/`_parse_*`) | ~80 |

- `risk_level`/`_looks_*` 下沉 `formatting.py`,避免 `view_text ↔ view_format` 互依赖(保 DAG 无环)。
- **子窗口 Mixin(用户已选)**:`windows/` 包内 `WatchlistMixin`/`ComparisonMixin`/`AlertMixin`,方法体原样搬入,`class StockAdvisorApp(WatchlistMixin, …)`;`self` 契约不变 → `hasattr(...)`/`self.app.<widget>` 测试全部保留。**监控环(`_monitor_*`/`_poll_monitor`)留 `app.py`**(它是后台服务非窗口 UI)。先抽解耦最彻底的对比窗,再自选,最后预警。
- **顺序**:先纯函数(theme→layout→formatting→view_text/view_format→sample_data/input_validate,零行为变化、削 ~1150 行),后子窗口 Mixin(再削 ~500 行,触及 GUI 测试单独进行)。
- app.py 最终 ~2400 行,聚焦界面组装/线程调度/渲染。

## WS6 · 打包 & git 卫生

- 新增 `.gitignore`:`__pycache__/`、`*.py[cod]`、`/build/`、`/dist/`。
- 首次提交前把已 staged 的 `~41 个 .pyc`、整棵 `build/`(含内嵌本机绝对路径的自动生成 `.spec`)、`build/pyinstaller/*.exe`、`dist/股市锦囊.exe`、`dist/使用说明.html` **移出暂存**(`git rm --cached`,不删工作区文件)。保留入库:全部源码、`assets/a_stock_strategy.ico`、`docs/`、`main.py`、`build_exe.py`、脚本、`requirements-build.txt`、`README.md`、`AGENTS.md`。
- `build_exe.py:43` `--add-data` 分隔符硬编码 `;` → 改用 `os.pathsep`(修 POSIX 构建)。
- 复核 `build_exe.py` 写边界(已有 `_remove_dir` 拒删项目外路径,保持);`build.bat/build.sh/run.bat/run.sh` 保持正确。
- 打包后自验:`dist\股市锦囊.exe --self-test` 退出码 0 且打印 `SELF_TEST_OK`。

## 测试策略

- **TDD**:先写失败测试再实现;纯逻辑必单测,GUI 用 headless(`Tk()` + `withdraw()`)覆盖关键布局/交互。
- **新增覆盖**:WS1 运行期几何回归(注入 scaling/工作区 → 断言居中与尺寸夹制);WS2 绘制度量纯函数(字号/缩放 → 坐标,断言无重叠);WS3 结构断言(合并后的结论卡/价格卡存在、空态折叠);WS4 各修复项(参数交叉校验、免责唯一、字段标签映射、取整一致)。
- **回归**:现有 390 测试保持全绿;每个拆分步骤后 `python -m unittest discover -s tests`。
- **语法**:`python -m py_compile main.py build_exe.py src/stock_advisor/*.py`。
- **真机自检**:整改后重新启动 GUI,确认窗口居中、尺寸合适、无重叠/裁切(截图核验,沿用 memory 记录的 4K@250% 验证法)。

## 推进顺序(阶段)

0. **git 卫生**:`.gitignore` + 移出构建产物(先做,避免后续每步都在二进制上翻搅)。
1. **抽纯函数模块**(WS5 前半):theme→layout→formatting→view_text/view_format→sample_data/input_validate;每步全绿。
2. **WS1 窗口几何 & DPI**:删 `scale_work_area_for_tk`,引入 `ui_scale`,补运行期几何测试。
3. **WS2 DPI-稳健渲染**:`scale()` 铺开 + 文字度量排布,修重叠/裁切/溢出。
4. **WS3 布局重构 & 视觉统一**:合并冗余、折叠空态、统一卡片/间距/字号、子窗口公共构件。
5. **WS4 功能补漏**:档位说明显示、参数交叉校验、免责收敛、资金流入队、字段标签、取整、旧文档指引;**重生成技术报告 HTML**。
6. **WS5 后半 子窗口 Mixin**:对比→自选→预警;监控环留 app.py。
7. **构建自验 + 真机截图核验 + 收尾**。

每阶段独立可交付、测试全绿、可回滚。

## 交付物

- 整改后的 `src/stock_advisor/`(app.py 瘦身 + 7 个纯函数模块 + `windows/` Mixin 包)、`main.py`、`build_exe.py`。
- `.gitignore`;干净的提交历史(不含构建产物/二进制)。
- 重生成的 `docs/stock_advisor_technical_stack_report.html`;更新的 `README.md`/`manual.py`(→ `dist/使用说明.html` 随构建重生成)。
- `dist/股市锦囊.exe`(按需构建,不入库)。

## 非目标(本次不做)

- 不做整套视觉语言重设计(不换配色体系/字体家族)。
- 不改核心决策模型、数据源接口、选股预设的算法语义。
- 不新增功能特性(资金流/基本面筛选等二期项不动)。
- 不改运行期依赖边界(仍纯标准库)。
