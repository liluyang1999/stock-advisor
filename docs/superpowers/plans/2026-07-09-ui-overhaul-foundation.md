# 界面整改 P1 · 地基(git 卫生 + 纯函数模块抽取)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理首次提交的 git 卫生,并把 `app.py`(4056 行)中约 1150 行纯函数按依赖顺序抽成 7 个独立模块,`app.py` 回归"只做界面/线程/渲染",全程零行为变化、测试全绿。

**Architecture:** 纯机械重构。新模块**只被 app.py 依赖、绝不 `import app`**,依赖单向无环(`theme` → `layout`/`formatting` → `view_text`/`view_format` → `sample_data`/`input_validate`)。`app.py` 用 `from .模块 import 名字` **真名 re-export**,使 `tests/*` 现有 `from stock_advisor.app import X` 与类方法体内裸名调用**零改动**;每抽一个模块即跑全套 390 测试确认仍绿。

**Tech Stack:** Python 3.14 标准库、tkinter、`unittest`、PyInstaller(仅构建期)、git。

## Global Constraints

- 运行期只用 Python 标准库;构建期只允许 `pip install pyinstaller`。
- 新模块**禁止 `import app`**;`app.py` 用 `from .模块 import (名字, …)`(真名,不用 `import 模块`)re-export,保持测试与方法体裸名调用可解析。
- 配色 A 股本土:红=涨/买、绿=跌/卖(本计划不改任何配色常量的值,仅搬家)。
- 每个 Task 结束前必须:`python -m unittest discover -s tests` 全绿 **且** `python -m py_compile main.py build_exe.py src/stock_advisor/*.py` 无错。
- 本计划**零行为变化**:被搬函数一律**逐字**移动,不改实现;`scale_work_area_for_tk` 照搬(它的删除属 P2,不在本计划)。
- 每条 commit message 末尾附 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 当前分支已有一个提交(设计 spec);本计划的实现应在专用特性分支/worktree 上进行(执行时由 using-git-worktrees 建立)。

---

## File Structure

**新建:**
- `.gitignore` — 忽略字节码与构建产物。
- `src/stock_advisor/theme.py` — UI 常量单一真源(颜色/尺寸/表列/排序序/免责/样例输入)。仅依赖 `pathlib`。
- `src/stock_advisor/layout.py` — 居中/工作区/内容带几何 + `active_mode_action`。零第三方依赖。
- `src/stock_advisor/formatting.py` — 数值强制、低层格式化、`risk_level`、文本谓词。依赖 `math`、`models`、`theme`。
- `src/stock_advisor/view_text.py` — 面向用户的整块文本构建 + 文案改写。依赖 `formatting`、`theme`、`models`、`policy`、`backtest`。
- `src/stock_advisor/view_format.py` — 行/表/剪贴板格式化 + 行/详情标签配色。依赖 `formatting`、`theme`、`models`、`compare`。
- `src/stock_advisor/sample_data.py` — 离线样例/空态占位数据。依赖 `engine`、`symbols`、`models`。
- `src/stock_advisor/input_validate.py` — 输入解析与可调项校验。依赖 `formatting`。

**修改:**
- `src/stock_advisor/app.py` — 移除被抽函数/常量,替换为 `from .模块 import (…)` re-export 行(保持文件内其余代码不变)。
- `build_exe.py:43` — `--add-data` 分隔符 `;` → `os.pathsep`。

**依赖顺序(抽取先后)**:`theme` → `layout` → `formatting` → `view_text` → `view_format` → `sample_data` + `input_validate`。先抽最底层叶子,后抽依赖它们的模块,任何时刻测试可跑。

---

### Task 1: git 卫生 + 构建分隔符修复

**Files:**
- Create: `.gitignore`
- Modify: `build_exe.py:43`

**Interfaces:**
- Consumes: 无。
- Produces: 干净的 git 跟踪面(构建产物/字节码不再入库);`build_exe.py` 跨平台分隔符正确。

- [ ] **Step 1: 新建 `.gitignore`**

内容:
```gitignore
# Python 字节码
__pycache__/
*.py[cod]

# 构建与交付产物(靠 build_exe.py 按需重建)
/build/
/dist/

# 编辑器/系统杂项
.DS_Store
Thumbs.db
```

- [ ] **Step 2: 把已 staged 的构建产物/字节码移出暂存区(保留工作区文件)**

Run:
```bash
git rm -r --cached --quiet build dist
git ls-files -z '*.pyc' '__pycache__/*' | xargs -0 -r git rm --cached --quiet
git add .gitignore
```
说明:`--cached` 只从索引移除、不删工作区文件;`.gitignore` 保证它们此后为忽略态。

- [ ] **Step 3: 验证跟踪面干净**

Run: `git status --porcelain | grep -E '\.(pyc|exe|pyz|toc|pkg)$|^A  build/|^A  dist/' || echo CLEAN`
Expected: 打印 `CLEAN`(暂存区不再含 `.pyc`/`.exe`/`.pyz`/`.toc`/`.pkg` 或 `build/`、`dist/` 新增项)。

Run: `git check-ignore -q build dist && echo IGNORED`
Expected: 打印 `IGNORED`。

- [ ] **Step 4: 修 `build_exe.py:43` 的 `--add-data` 分隔符**

把硬编码的 `;` 改为 `os.pathsep`(文件顶部若未 `import os` 则补上)。当前:
```python
        f"{ICON_PATH};assets",
```
改为:
```python
        f"{ICON_PATH}{os.pathsep}assets",
```

- [ ] **Step 5: 校验**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`(390 tests)。

Run: `python -m py_compile main.py build_exe.py src/stock_advisor/*.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 6: 提交**

```bash
git add .gitignore build_exe.py
git commit -m "chore: add .gitignore, drop build artifacts from tracking, fix add-data separator"
```

---

### Task 2: 抽取 `theme.py`(UI 常量单一真源)

**Files:**
- Create: `src/stock_advisor/theme.py`
- Modify: `src/stock_advisor/app.py`(常量区约 47-98;顶部导入)

**Interfaces:**
- Consumes: 无(叶子模块)。
- Produces: 全部 UI 常量:`MAX_SYMBOLS, MONITOR_INTERVAL_MS, APP_TITLE, APP_ICON_FILENAME, INFO_WINDOW_SIZE, MAIN_MIN_SIZE, WINDOW_MAX_SIZE, WINDOW_WORKAREA_MARGIN, WINDOW_ALPHA, MAX_CONTENT_WIDTH, CONTENT_MARGIN, HEADER_LOGO_SIZE, MENU_BUTTON_SHORT_WIDTH, MENU_BUTTON_TOOL_WIDTH, PAGE_BG, CARD_BG, CARD_BORDER, INK, MUTED_INK, ACCENT, POS_COLOR, NEG_COLOR, FLAT_COLOR, POS_BG, NEG_BG, HOLD_BG, ACTION_BUTTON_LABELS, TABLE_MIN_VISIBLE_ROWS, TABLE_MAX_VISIBLE_ROWS, TABLE_EMPTY_VISIBLE_ROWS, DETAIL_NAV_SECTIONS, ASSET_DIR, SAMPLE_INPUT, DISCLAIMER, DETAIL_SECTION_TITLES, TABLE_COLUMNS, TABLE_COLUMN_INDEX, RISK_ORDER, ACTION_ORDER`。

- [ ] **Step 1: 创建 `theme.py`,逐字迁入常量**

把 `app.py` 常量区(约 47-98,即 `MAX_SYMBOLS` 到 `ACTION_ORDER`,含各注释)**逐字**剪切进新文件。`theme.py` 顶部加:
```python
"""UI 常量单一真源:颜色、尺寸、表列、排序序、免责声明、样例输入。仅依赖标准库。"""
from __future__ import annotations

from pathlib import Path
```
注:`ASSET_DIR = Path(__file__).resolve().parents[2] / "assets"` 依赖 `Path`,已在上面导入;`app.py` 里 `app_asset_path` 函数**保留在 app.py**(它读 `sys.frozen`)。

- [ ] **Step 2: 在 app.py 用 re-export 替换被删常量区**

在 app.py 原常量区位置写一行(真名 re-export,供测试与方法体裸名解析):
```python
from .theme import (
    MAX_SYMBOLS, MONITOR_INTERVAL_MS, APP_TITLE, APP_ICON_FILENAME, INFO_WINDOW_SIZE,
    MAIN_MIN_SIZE, WINDOW_MAX_SIZE, WINDOW_WORKAREA_MARGIN, WINDOW_ALPHA, MAX_CONTENT_WIDTH,
    CONTENT_MARGIN, HEADER_LOGO_SIZE, MENU_BUTTON_SHORT_WIDTH, MENU_BUTTON_TOOL_WIDTH,
    PAGE_BG, CARD_BG, CARD_BORDER, INK, MUTED_INK, ACCENT, POS_COLOR, NEG_COLOR, FLAT_COLOR,
    POS_BG, NEG_BG, HOLD_BG, ACTION_BUTTON_LABELS, TABLE_MIN_VISIBLE_ROWS, TABLE_MAX_VISIBLE_ROWS,
    TABLE_EMPTY_VISIBLE_ROWS, DETAIL_NAV_SECTIONS, ASSET_DIR, SAMPLE_INPUT, DISCLAIMER,
    DETAIL_SECTION_TITLES, TABLE_COLUMNS, TABLE_COLUMN_INDEX, RISK_ORDER, ACTION_ORDER,
)
```

- [ ] **Step 3: 跑全套测试确认仍绿**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`(390 tests)。若报 `ImportError`/`NameError`,核对是否有常量遗漏在 re-export 名单。

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile src/stock_advisor/theme.py src/stock_advisor/app.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/theme.py src/stock_advisor/app.py
git commit -m "refactor: extract UI constants into theme.py (re-export from app)"
```

---

### Task 3: 抽取 `layout.py`(几何纯函数)

**Files:**
- Create: `src/stock_advisor/layout.py`
- Modify: `src/stock_advisor/app.py`(约 414-554)

**Interfaces:**
- Consumes: 无。
- Produces: `compute_centered_geometry, compute_window_position, normalize_work_area_to_screen, choose_centering_screen_size, scale_work_area_for_tk, compute_centered_window, compute_content_band, active_mode_action`(签名与现状完全一致)。

- [ ] **Step 1: 创建 `layout.py`,逐字迁入 8 个函数**

把 app.py 中这 8 个函数**逐字**剪切进 `layout.py`:`compute_centered_geometry`(414)、`compute_window_position`(421)、`normalize_work_area_to_screen`(429)、`choose_centering_screen_size`(444)、`scale_work_area_for_tk`(458)、`compute_centered_window`(479)、`active_mode_action`(503)、`compute_content_band`(547)。文件顶部:
```python
"""窗口居中、工作区归一、内容带几何——纯数学,零依赖,便于单测。"""
from __future__ import annotations
```
注:这些函数只用内建 `int/max/min/round/float`,无需其它导入。`scale_work_area_for_tk` 照搬(P2 才删)。

- [ ] **Step 2: app.py re-export**

在原位置写:
```python
from .layout import (
    compute_centered_geometry, compute_window_position, normalize_work_area_to_screen,
    choose_centering_screen_size, scale_work_area_for_tk, compute_centered_window,
    compute_content_band, active_mode_action,
)
```

- [ ] **Step 3: 测试**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。(`tests/test_ui_polish.py` 直接 import 这些几何函数,是主要守门。)

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile src/stock_advisor/layout.py src/stock_advisor/app.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/layout.py src/stock_advisor/app.py
git commit -m "refactor: extract window/content geometry into layout.py"
```

---

### Task 4: 抽取 `formatting.py`(数值/格式原语 + risk_level + 谓词)

**Files:**
- Create: `src/stock_advisor/formatting.py`
- Modify: `src/stock_advisor/app.py`(类前约 167-341/365-378/648-701;类后 3889/3969-3981/4038-4056)

**Interfaces:**
- Consumes: `theme`(如 `risk_level` 可能用 `RISK_*`/阈值——若无引用则不导入)、`models`。
- Produces: `_finite_float, _positive_finite_float, _positive_finite_int, _safe_int, _fmt_decimal, _fmt_score_value, _fmt_plain_number, _fmt_whole_percent, _fmt_percent_points, _fmt_rate_percent, _fmt_backtest_return, _fmt_backtest_excess, _fmt_amount, _format_number, _spin_step, _fmt_yi, _flow_direction, _number_from_cell, _fmt, _fmt_percent, _fmt_percent_value, risk_level, _looks_risky, _looks_positive, _looks_negative`。

- [ ] **Step 1: 创建 `formatting.py`,逐字迁入原语函数**

从 app.py **逐字**剪切:`_fmt_rate_percent/_fmt_backtest_return/_fmt_backtest_excess`(167-185)、`_finite_float/_positive_finite_float/_positive_finite_int/_safe_int`(272-303)、`_fmt_decimal/_fmt_score_value/_fmt_plain_number/_fmt_whole_percent/_fmt_percent_points`(304-340)、`_fmt_yi/_flow_direction`(365-378)、`_fmt_amount/_format_number/_spin_step`(648-675)、`risk_level`(676-688);以及**类之后**的 `_number_from_cell`(3889)、`_looks_risky/_looks_positive/_looks_negative`(3969-3981)、`_fmt/_fmt_percent/_fmt_percent_value`(4038-4056)。文件顶部:
```python
"""数值强制、低层格式化、风险分级与文本谓词——纯函数,供 view_text / view_format 复用。"""
from __future__ import annotations

import math

from .models import AnalysisResult  # 若 risk_level 类型标注需要;按实际引用增减
```
注:导入按被搬函数**实际引用**增减(如某函数只用 `math` 则仅 `import math`)。`risk_level`/`_looks_*` 放在此最底层叶子,避免 `view_text ↔ view_format` 互相依赖。

- [ ] **Step 2: app.py re-export**

在类前被删块位置写:
```python
from .formatting import (
    _finite_float, _positive_finite_float, _positive_finite_int, _safe_int,
    _fmt_decimal, _fmt_score_value, _fmt_plain_number, _fmt_whole_percent, _fmt_percent_points,
    _fmt_rate_percent, _fmt_backtest_return, _fmt_backtest_excess,
    _fmt_amount, _format_number, _spin_step, _fmt_yi, _flow_direction, _number_from_cell,
    _fmt, _fmt_percent, _fmt_percent_value, risk_level, _looks_risky, _looks_positive, _looks_negative,
)
```
删掉类后对应的原定义(它们现由 import 提供)。

- [ ] **Step 3: 测试**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。若某函数在 `formatting.py` 里因缺导入报 `NameError`,补齐该模块顶部导入。

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile src/stock_advisor/formatting.py src/stock_advisor/app.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/formatting.py src/stock_advisor/app.py
git commit -m "refactor: extract numeric/format primitives into formatting.py"
```

---

### Task 5: 抽取 `view_text.py`(用户文本构建 + 文案改写)

**Files:**
- Create: `src/stock_advisor/view_text.py`
- Modify: `src/stock_advisor/app.py`(约 158-238、379-394、585-647、702-775、840-954;类后 3878-3968)

**Interfaces:**
- Consumes: `formatting`(`_fmt_*`、`_looks_*`)、`theme`(`DISCLAIMER` 等)、`models`、`policy`、`backtest`。
- Produces: `level_summary, build_position_plan_text, build_backtest_text, build_spectrum_text, build_fund_flow_text, build_screener_overview, build_recommendation_header, build_snapshot_summary, build_snapshot_detail, build_visual_summary, build_detail_text, summarize_results, normalize_symbol_input_text, build_portfolio_overview, build_help_sections, build_manual_text, build_strategy_sections, build_strategy_explanation_text, _focus_symbols, _friendly_factor_name, _friendly_verdict, _plain_text`。

- [ ] **Step 1: 创建 `view_text.py`,逐字迁入文本构建函数**

从 app.py **逐字**剪切:`level_summary`(158)、`build_position_plan_text/build_backtest_text/build_spectrum_text`(186-238)、`build_fund_flow_text`(379-394)、`build_screener_overview`(585-592)、`build_recommendation_header/build_snapshot_summary/build_snapshot_detail`(604-647)、`build_visual_summary/build_detail_text`(702-745)、`summarize_results/normalize_symbol_input_text/build_portfolio_overview`(746-775)、`build_help_sections/build_manual_text/build_strategy_sections/build_strategy_explanation_text`(840-954);以及**类之后**的 `_focus_symbols`(3878)、`_friendly_factor_name`(3900)、`_friendly_verdict`(3915)、`_plain_text`(3939)。顶部按实际引用导入(典型):
```python
"""面向用户的文本构建与文案改写——纯函数。"""
from __future__ import annotations

from .formatting import (
    _fmt_decimal, _fmt_plain_number, _fmt_percent_points, _fmt_rate_percent,
    _fmt_backtest_return, _fmt_backtest_excess, _fmt_yi, _flow_direction, _looks_risky,
)
from .theme import DISCLAIMER
# 其余按被搬函数实际引用补:models / policy / backtest 中的类型与 level_spec/spectrum 等
```

- [ ] **Step 2: app.py re-export**

替换被删块:
```python
from .view_text import (
    level_summary, build_position_plan_text, build_backtest_text, build_spectrum_text,
    build_fund_flow_text, build_screener_overview, build_recommendation_header,
    build_snapshot_summary, build_snapshot_detail, build_visual_summary, build_detail_text,
    summarize_results, normalize_symbol_input_text, build_portfolio_overview,
    build_help_sections, build_manual_text, build_strategy_sections, build_strategy_explanation_text,
    _focus_symbols, _friendly_factor_name, _friendly_verdict, _plain_text,
)
```
删掉类后 `_focus_symbols/_friendly_*/_plain_text` 的原定义。

- [ ] **Step 3: 测试(重点核对前后向引用已消除)**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。注意:`build_detail_text` 调 `_plain_text/_friendly_*`(现同模块)、`build_portfolio_overview` 调 `_focus_symbols`(现同模块)。若类方法体(如 `_draw_visual`)调用了移走的 `_plain_text` 报 `NameError`,确认 app.py 的 re-export 名单已含它。

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile src/stock_advisor/view_text.py src/stock_advisor/app.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/view_text.py src/stock_advisor/app.py
git commit -m "refactor: extract user-facing text builders into view_text.py"
```

---

### Task 6: 抽取 `view_format.py`(行/表/剪贴板格式化 + 标签配色)

**Files:**
- Create: `src/stock_advisor/view_format.py`
- Modify: `src/stock_advisor/app.py`(约 341-364、395-413、555-584、689-701、776-839;类后 3986-4035)

**Interfaces:**
- Consumes: `formatting`(`_number_from_cell`、`risk_level` 等)、`theme`(`POS_COLOR/NEG_COLOR/FLAT_COLOR/TABLE_COLUMN_INDEX/ACTION_ORDER/RISK_ORDER`)、`models`、`compare`。
- Produces: `watchlist_rows, format_comparison_row, snapshot_display, format_recommendation_row, format_result_row, table_sort_key, result_row_tags, detail_line_tags, _score_color, _action_color, format_results_for_clipboard, format_results_as_csv, format_table_rows_for_clipboard, format_table_rows_as_csv`(及 `_FACTOR_SCORE_RE`)。

- [ ] **Step 1: 创建 `view_format.py`,逐字迁入格式化/标签函数**

从 app.py **逐字**剪切:`watchlist_rows`(341)、`format_comparison_row`(395)、`snapshot_display`(555)、`format_recommendation_row`(565)、`format_result_row/result_row_tags`(689-795 中的这两个)、`table_sort_key`(776)、`format_results_for_clipboard/format_results_as_csv/format_table_rows_for_clipboard/format_table_rows_as_csv`(796-839);以及**类之后**的 `_FACTOR_SCORE_RE` + `detail_line_tags`(3986-4018)、`_score_color/_action_color`(4021-4035)。顶部(典型):
```python
"""行/表/剪贴板格式化与行/详情标签配色——纯函数。"""
from __future__ import annotations

import csv
import io
import re

from .formatting import _number_from_cell, risk_level, _fmt_decimal
from .theme import POS_COLOR, NEG_COLOR, FLAT_COLOR, TABLE_COLUMN_INDEX, ACTION_ORDER, RISK_ORDER
# 其余按实际引用补:models 类型、compare.ComparisonRow
```
注:`table_sort_key` 用 `_number_from_cell`、`result_row_tags`/`format_result_row` 用 `risk_level`——均来自 `formatting`(叶子),无环。

- [ ] **Step 2: app.py re-export**

```python
from .view_format import (
    watchlist_rows, format_comparison_row, snapshot_display, format_recommendation_row,
    format_result_row, table_sort_key, result_row_tags, detail_line_tags, _score_color, _action_color,
    format_results_for_clipboard, format_results_as_csv, format_table_rows_for_clipboard,
    format_table_rows_as_csv,
)
```
删掉类后 `detail_line_tags/_score_color/_action_color/_FACTOR_SCORE_RE` 原定义。

- [ ] **Step 3: 测试**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。(`tests/test_compare.py` 的 `format_comparison_row`、`test_ui_polish.py` 的 `detail_line_tags`、`test_app_helpers.py` 的 `format_result_*` 守门。)

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile src/stock_advisor/view_format.py src/stock_advisor/app.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/view_format.py src/stock_advisor/app.py
git commit -m "refactor: extract row/table/clipboard formatting into view_format.py"
```

---

### Task 7: 抽取 `sample_data.py` + `input_validate.py`

**Files:**
- Create: `src/stock_advisor/sample_data.py`、`src/stock_advisor/input_validate.py`
- Modify: `src/stock_advisor/app.py`(约 108-157、593-603;239-271、508-546)

**Interfaces:**
- Consumes: `sample_data` ← `engine/symbols/models`;`input_validate` ← `formatting`(如 `_format_number`)。
- Produces:
  - `sample_data`: `_sample_quote_history, make_sample_analysis, make_sample_measurement, make_sample_history, make_sample_recommendation`。
  - `input_validate`: `_parse_optional_positive, _parse_optional_positive_int, _parse_alert_threshold, is_partial_number, validate_tunable`。

- [ ] **Step 1: 创建 `sample_data.py`,逐字迁入样例函数**

剪切 `_sample_quote_history`(108)、`make_sample_analysis`(144)、`make_sample_measurement`(149)、`make_sample_history`(154)、`make_sample_recommendation`(593)。顶部按实际引用导入 `engine`/`symbols`/`models` 中所需符号。

- [ ] **Step 2: 创建 `input_validate.py`,逐字迁入校验函数**

剪切 `_parse_optional_positive`(239)、`_parse_optional_positive_int`(250)、`_parse_alert_threshold`(264)、`is_partial_number`(508)、`validate_tunable`(527)。顶部:
```python
"""输入解析与选股可调项校验——纯函数。"""
from __future__ import annotations

import math

from .formatting import _format_number
```
(`validate_tunable` 用 `_format_number` 组织报错文案;`is_partial_number` 无外部依赖。)

- [ ] **Step 3: app.py re-export**

```python
from .sample_data import (
    _sample_quote_history, make_sample_analysis, make_sample_measurement,
    make_sample_history, make_sample_recommendation,
)
from .input_validate import (
    _parse_optional_positive, _parse_optional_positive_int, _parse_alert_threshold,
    is_partial_number, validate_tunable,
)
```

- [ ] **Step 4: 测试 + 语法检查**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。(`test_app_helpers` 的 `make_sample_*`、`test_ui_polish` 的 `is_partial_number/validate_tunable/make_sample_recommendation` 守门。)
Run: `python -m py_compile src/stock_advisor/sample_data.py src/stock_advisor/input_validate.py src/stock_advisor/app.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/sample_data.py src/stock_advisor/input_validate.py src/stock_advisor/app.py
git commit -m "refactor: extract sample data and input validation modules"
```

---

### Task 8: 收尾核对(app.py 瘦身达标 + 全绿 + 自检)

**Files:**
- Modify(如有):`src/stock_advisor/app.py`(清理死导入 `board_of`/`default_values` 若确未使用)

**Interfaces:**
- Consumes: 前 7 个模块。
- Produces: app.py ≈ 2900 行、聚焦界面/线程/渲染;7 个纯函数模块可独立导入。

- [ ] **Step 1: 确认 app.py 行数显著下降**

Run: `wc -l src/stock_advisor/app.py`
Expected: 明显低于 4056(目标 ~2900±)。

- [ ] **Step 2: 清理确认无用的死导入(仅当 grep 证实未被引用)**

Run: `grep -n "board_of\|default_values" src/stock_advisor/app.py`
若仅出现在顶部 import 行、别处无引用,则删除该 import;否则保留。(`ACTION_BUTTON_LABELS` 已随 theme 迁移,勿动。)

- [ ] **Step 3: 各新模块可独立导入(无环、无 tkinter 依赖)**

Run: `python -c "import stock_advisor.theme, stock_advisor.layout, stock_advisor.formatting, stock_advisor.view_text, stock_advisor.view_format, stock_advisor.sample_data, stock_advisor.input_validate; print('IMPORT_OK')"`
(在 `src/` 于 `sys.path` 时;或 `cd src && python -c ...`)
Expected: `IMPORT_OK`,且过程中无 `ImportError`(证明未 `import app`、无循环)。

- [ ] **Step 4: 全套测试 + 离线自检 + 语法**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`(390 tests)。
Run: `python main.py --self-test`
Expected: 退出码 0,打印 `SELF_TEST_OK …`。
Run: `python -m py_compile main.py build_exe.py src/stock_advisor/*.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 5: 提交(如有清理)**

```bash
git add src/stock_advisor/app.py
git commit -m "refactor: drop dead imports after module extraction"
```

---

## Self-Review

**1. Spec 覆盖(对应 spec 阶段 0-1 / WS5 前半 / WS6):**
- git 卫生(.gitignore + 移出构建产物)→ Task 1 ✓
- `--add-data` 分隔符 → Task 1 ✓
- 7 个纯函数模块(theme/layout/formatting/view_text/view_format/sample_data/input_validate)→ Task 2-7 ✓
- re-export 保测试全绿 → 每 Task Step 3/4 ✓
- app.py 回归"界面/线程/渲染"、行数下降 → Task 8 ✓
- 子窗口 Mixin(WS5 后半)→ **不在本计划**,属 P4(spec 阶段 6),已在 spec 明确;本计划范围仅纯函数抽取 ✓

**2. 占位符扫描:** 无 TBD/TODO;每步给出确切命令与期望输出。抽取步骤按"逐字搬运 + 实际引用补导入"描述(机械重构不宜重复 1150 行原码),并对每个可能的 `NameError`/循环给出定位指引。

**3. 类型/名称一致性:** 各模块 Produces 的函数名与 app.py re-export 名单逐一对应;`risk_level`/`_looks_*` 统一落在 `formatting`(被 view_text/view_format 共用),避免互依赖;`scale_work_area_for_tk` 本计划仅搬运不删(删除属 P2),名称一致。

**若执行中发现某函数的真实依赖跨越了预设模块边界**(例如 view_text 需要某个我归到 view_format 的 helper),按"下沉到 formatting 叶子"或"补 app.py re-export"就地消解,不改变对外行为。
