# 界面整改 P2 · 窗口几何/DPI + DPI-稳健渲染 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治高 DPI 下"窗口只占屏 1/3、缩在左上角"的运行期 bug——让窗口在屏幕工作区正中央、尺寸随 DPI 自适应到合适大小、四边留白均匀;并消除因"pt 字体放大而画布坐标固定"导致的文字重叠/裁切/溢出。

**Architecture:** 进程已由 `main.py` 开启 DPI 感知,故 **Tk 的 `geometry()` 单位 == `SPI_GETWORKAREA` 单位 == 物理像素**(同一坐标系)。删除把工作区÷2.5 的 `scale_work_area_for_tk`(那是把窗口缩小的元凶),改为:窗口按**物理工作区**居中,逻辑尺寸常量(min/max/margin/内容带宽)乘 `ui_scale` 后再夹制。渲染侧引入 `self._sc(px)=round(px*ui_scale)`,把所有硬编码画布坐标/尺寸随字体一起放大,坐标与放大字体重新对齐。几何与文本布局尽量抽成 layout.py 纯函数并单测。

**Tech Stack:** Python 3.14 标准库、tkinter、`ctypes`(Windows DPI/工作区)、`unittest`。

## Global Constraints

- 运行期只用 Python 标准库;不新增运行期依赖。
- **不改任何数值决策/业务逻辑**;本阶段只动窗口几何与绘制/样式的像素量。
- DPI 因子单一真源:`layout.ui_scale(tk_scaling)`(96 DPI→1.0,250%→2.5,按 0.25 取整);渲染侧 `self._ui_scale`/`self._sc()` 由它派生。
- 降级:DPI 感知失败(极老 Windows)时 `tk scaling≈1.333`→`ui_scale=1.0`,几何/渲染退化为原逻辑,不得崩溃。
- 每个 Task 结束前:`python -m unittest discover -s tests` 全绿(当前 390,允许因新增测试而增加)**且** `python -m py_compile main.py build_exe.py src/stock_advisor/*.py` 无错。
- 纯函数用 TDD(先失败测试再实现);GUI 用 headless(`Tk()`+`withdraw()`)。
- 每条 commit message 末尾附 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 分支 `feat/ui-overhaul-foundation`(承载整个 overhaul);不动 main。

---

## File Structure

**修改:**
- `src/stock_advisor/layout.py` — 新增 `ui_scale()`、`compute_main_geometry()`;删除 `scale_work_area_for_tk`(P1 仅搬运,此处删除)。
- `src/stock_advisor/app.py` — `_apply_centered_geometry`(1556)、`_screen_work_area`(1589):停止÷2.5、改用物理工作区 + `compute_main_geometry`;删除对 `scale_work_area_for_tk` 的 re-export;`__init__` 计算 `self._ui_scale`;新增 `_sc()`;`_configure_styles`(870)、`_build_results_region`(画布 height)、`_draw_empty_visual`(2622)、`_draw_visual`(2845)、`_draw_spectrum_strip`(2493)、`_on_kline_motion`(513)、`_refresh_table_height`(2605)、`_apply_content_band`(1698)、选股页 `wraplength` 等:像素量改走 `self._sc()`/度量。
- `tests/test_ui_polish.py` — 删除 `scale_work_area_for_tk` 的导入与用例;新增 `ui_scale`/`compute_main_geometry` 用例。
- `tests/test_gui_layout.py` — 新增窗口几何集成测试(桩化工作区/缩放)与画布缩放断言。

**新增(可选):** 若某绘制布局计算复杂,抽成 layout.py 纯函数(如 `empty_visual_layout(scale, line_h) -> dict`)并单测。

依赖方向不变:layout.py 仍是零依赖纯函数;app.py 依赖 layout/theme。

---

### Task 1: `ui_scale()` + `compute_main_geometry()` 纯函数(WS1 核心 + 回归测试)

**Files:**
- Modify: `src/stock_advisor/layout.py`
- Test: `tests/test_ui_polish.py`

**Interfaces:**
- Produces:
  - `ui_scale(tk_scaling: float) -> float` — 由 Tk scaling 得 Windows DPI 因子;96DPI→1.0,按 0.25 取整,下限 1.0,非法输入→1.0。
  - `compute_main_geometry(work_left, work_top, work_w, work_h, ui_scale_factor, min_w, min_h, max_w, max_h, margin, frame_w=0, frame_h=0) -> tuple[int,int,int,int]` — 在**物理工作区**内居中,逻辑常量按 `ui_scale_factor` 放大后夹制;返回 `(win_w, win_h, abs_x, abs_y)`(abs 已含工作区原点偏移)。内部复用既有 `compute_centered_window`。
- Consumes: 既有 `compute_centered_window`。

- [ ] **Step 1: 写失败测试(高 DPI 回归 + 100% 不变 + 降级)**

在 `tests/test_ui_polish.py` 增加:
```python
from stock_advisor.layout import ui_scale, compute_main_geometry, compute_centered_window

def test_ui_scale_from_tk_scaling():
    assert ui_scale(96/72) == 1.0            # 100%
    assert ui_scale(3.3366) == 2.5           # 250% (4K 本机)
    assert ui_scale(2.0) == 1.5              # 150%
    assert ui_scale("bad") == 1.0            # 非法→1.0
    assert ui_scale(0.5) == 1.0              # 下限 1.0

def test_main_geometry_high_dpi_centers_and_fills():
    # 4K@250%: 物理工作区 3840x2040, ui_scale 2.5 —— 复现被修的 bug 场景
    win_w, win_h, x, y = compute_main_geometry(
        0, 0, 3840, 2040, 2.5, 1000, 680, 1600, 1600, 72, frame_w=16, frame_h=39,
    )
    assert win_w >= 3000 and win_h >= 1600   # 旧 bug 是 1376x680,现在填满
    assert x > 0 and y > 0                    # 旧 bug 是 +72+48 贴左上;现居中
    assert abs((3840 - (win_w + 16)) // 2 - x) <= 1   # 四边留白均匀(按外框)
    assert abs((2040 - (win_h + 39)) // 2 - y) <= 1

def test_main_geometry_no_scaling_matches_plain_centering():
    # ui_scale=1.0 时等价于直接 compute_centered_window + 原点偏移
    got = compute_main_geometry(0, 0, 1536, 816, 1.0, 1000, 680, 1600, 1600, 72, 16, 39)
    base = compute_centered_window(1536, 816, 72, 1600, 1600, 1000, 680, 16, 39)
    assert got == (base[0], base[1], base[2], base[3])
```

- [ ] **Step 2: 运行,确认失败**

Run: `python -m unittest tests.test_ui_polish -v 2>&1 | grep -E "ui_scale|main_geometry" | head`
Expected: FAIL / ImportError(`ui_scale`/`compute_main_geometry` 未定义)。

- [ ] **Step 3: 实现两个纯函数**

在 `layout.py` 末尾(`compute_content_band` 后)加:
```python
def ui_scale(tk_scaling: float) -> float:
    """Windows DPI 缩放因子:Tk scaling(点→像素)换算,96 DPI=1.0,按 0.25 档位取整。"""
    try:
        raw = float(tk_scaling) * 72.0 / 96.0
    except (TypeError, ValueError):
        return 1.0
    if raw <= 1.05:
        return 1.0
    return max(1.0, round(raw * 4) / 4)


def compute_main_geometry(
    work_left: int, work_top: int, work_w: int, work_h: int, ui_scale_factor: float,
    min_w: int, min_h: int, max_w: int, max_h: int, margin: int,
    frame_w: int = 0, frame_h: int = 0,
) -> tuple[int, int, int, int]:
    """DPI 感知进程里 geometry 单位=物理像素:在物理工作区内按外框居中,逻辑尺寸常量
    (min/max/margin)先乘 ui_scale_factor 再夹制,使窗口随 DPI 成比例填满而非缩成逻辑像素。
    返回 (客户区宽, 客户区高, 外框左上角绝对 x, 绝对 y)。"""
    s = max(1.0, float(ui_scale_factor))
    win_w, win_h, off_x, off_y = compute_centered_window(
        work_w, work_h, round(margin * s),
        round(max_w * s), round(max_h * s), round(min_w * s), round(min_h * s),
        frame_w, frame_h,
    )
    return win_w, win_h, int(work_left) + off_x, int(work_top) + off_y
```

- [ ] **Step 4: 运行,确认通过**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`(390 + 3 新用例)。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/layout.py tests/test_ui_polish.py
git commit -m "feat(layout): add ui_scale + compute_main_geometry for DPI-aware centering"
```

---

### Task 2: 接入 app.py 几何路径、删除 `scale_work_area_for_tk`(WS1 集成)

**Files:**
- Modify: `src/stock_advisor/app.py`(`_apply_centered_geometry` 1556、`_screen_work_area` 1589、layout re-export 行)
- Modify: `src/stock_advisor/layout.py`(删 `scale_work_area_for_tk`)
- Modify: `tests/test_ui_polish.py`(删 `scale_work_area_for_tk` 用例/导入)
- Test: `tests/test_gui_layout.py`(新增几何集成测试)

**Interfaces:**
- Consumes: `ui_scale`、`compute_main_geometry`(Task 1);既有 `choose_centering_screen_size`、`normalize_work_area_to_screen`。
- Produces: 主窗口在真机上居中且尺寸自适应;`_screen_work_area` 返回**物理**工作区(不再÷2.5)。

- [ ] **Step 1: 写失败集成测试(桩化工作区+缩放)**

在 `tests/test_gui_layout.py` 增加(headless,桩掉平台相关取值以复现 4K@250%):
```python
def test_apply_centered_geometry_high_dpi(self):
    import tkinter as tk
    from stock_advisor.app import StockAdvisorApp
    root = tk.Tk(); root.withdraw()
    try:
        app = StockAdvisorApp(root)
        app._screen_work_area = lambda w: (0, 0, 3840, 2040)   # 物理工作区
        app._frame_extents = lambda w: (16, 39)
        app._tk_scaling = lambda w: 3.3366                     # 250%
        app._apply_centered_geometry(root)
        root.update_idletasks()
        geo = root.geometry()                                   # 形如 "3464x1700+188+150"
        wh, x, y = geo.split("+")[0], int(geo.split("+")[1]), int(geo.split("+")[2])
        w, h = (int(v) for v in wh.split("x"))
        self.assertGreaterEqual(w, 3000)      # 非旧 bug 的 1376
        self.assertGreaterEqual(h, 1600)      # 非旧 bug 的 680
        self.assertGreater(x, 0); self.assertGreater(y, 0)     # 居中,非左上角
    finally:
        root.destroy()
```
(若 `StockAdvisorApp` 尚无 `_tk_scaling` 方法,本测试的桩会在 Step 3 实现后才生效——先让它因断言失败或 AttributeError 而 FAIL。)

- [ ] **Step 2: 运行,确认失败**

Run: `python -m unittest tests.test_gui_layout -k high_dpi -v 2>&1 | tail -15`
Expected: FAIL(当前几何路径÷2.5,窗口 ~1376x680 或 AttributeError)。

- [ ] **Step 3: 改 app.py 几何路径**

(a) 新增小助手(放在 `_screen_work_area` 附近):
```python
    def _tk_scaling(self, window: tk.Misc) -> float:
        try:
            return float(window.tk.call("tk", "scaling"))
        except (tk.TclError, ValueError, TypeError):
            return 96 / 72
```
(b) `_apply_centered_geometry` 改为:
```python
    def _apply_centered_geometry(self, window: tk.Tk | tk.Toplevel) -> None:
        left, top, work_w, work_h = self._screen_work_area(window)
        frame_w, frame_h = self._frame_extents(window)
        factor = ui_scale(self._tk_scaling(window))
        win_w, win_h, x, y = compute_main_geometry(
            left, top, work_w, work_h, factor,
            MAIN_MIN_SIZE[0], MAIN_MIN_SIZE[1], WINDOW_MAX_SIZE[0], WINDOW_MAX_SIZE[1],
            WINDOW_WORKAREA_MARGIN, frame_w, frame_h,
        )
        window.geometry(f"{win_w}x{win_h}+{x}+{y}")
```
(c) `_screen_work_area` 停止÷2.5:删除对 `scale_work_area_for_tk` 的调用,SPI 分支直接 `return normalize_work_area_to_screen(rect.left, rect.top, width, height, screen_w, screen_h)`;兜底分支 `return 0, 0, screen_w, screen_h`。(保留 `choose_centering_screen_size` 多屏处理。)
(d) 更新 app.py 顶部 `from .layout import (...)`:加 `ui_scale, compute_main_geometry`,删 `scale_work_area_for_tk`。

- [ ] **Step 4: 删除 `scale_work_area_for_tk` 及其用例**

- `layout.py`:删除 `scale_work_area_for_tk` 定义(约 49-67)。
- `tests/test_ui_polish.py`:删除 `scale_work_area_for_tk` 的导入与所有相关 `test_*`。
- 全仓确认无残留引用:`grep -rn scale_work_area_for_tk src tests` → 应为空。

- [ ] **Step 5: 运行全套 + 集成测试**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。
Run: `python -m py_compile main.py build_exe.py src/stock_advisor/*.py && echo COMPILE_OK`
Expected: `COMPILE_OK`。

- [ ] **Step 6: 提交**

```bash
git add src/stock_advisor/app.py src/stock_advisor/layout.py tests/test_ui_polish.py tests/test_gui_layout.py
git commit -m "fix(ui): center main window at proper size on high-DPI; drop broken work-area downscale"
```

---

### Task 3: `self._ui_scale`/`self._sc()` + 缩放固定画布/控件尺寸(WS2 尺寸)

**Files:**
- Modify: `src/stock_advisor/app.py`(`__init__`、`_configure_styles` 870、`_build_results_region` 画布、`_apply_content_band` 1698、选股页 wraplength、进度条/滚动条/spinbox)
- Test: `tests/test_gui_layout.py`

**Interfaces:**
- Consumes: `ui_scale`、`self._tk_scaling`。
- Produces: `self._ui_scale: float`、`self._sc(px:int)->int`(=`round(px*self._ui_scale)`);所有固定画布高/行高/装饰尺寸随 DPI 放大。

- [ ] **Step 1: 写失败测试(画布高随 DPI 放大)**

在 `tests/test_gui_layout.py` 增加:构造 app,强制 `app._ui_scale = 2.5` 后重建结果区(或直接断言 `app._sc(300) == 750`、`app._sc(48) == 120`、`app._sc(32) == 80`);并断言 `visual`/`kline_canvas` 的 `height` 配置 == `app._sc(300)`、`spectrum_canvas` 高 == `app._sc(48)`。
```python
def test_sc_scales_canvas_dims(self):
    ...
    app._ui_scale = 2.5
    self.assertEqual(app._sc(300), 750)
    self.assertEqual(app._sc(48), 120)
    # 若画布高在构建期读取,验证构建时用了 _sc(...)(见实现)
```

- [ ] **Step 2: 运行,确认失败(`_sc`/`_ui_scale` 不存在)**

Run: `python -m unittest tests.test_gui_layout -k sc_scales -v 2>&1 | tail -10`
Expected: FAIL / AttributeError。

- [ ] **Step 3: 实现 `_ui_scale`/`_sc` 并铺开到固定尺寸**

(a) `__init__` 里(在 `_build_ui` 之前)计算一次:
```python
        self._ui_scale = ui_scale(self._tk_scaling(root))
```
(b) 加方法:
```python
    def _sc(self, px: float) -> int:
        return int(round(px * self._ui_scale))
```
(c) 把这些**固定像素**改走 `self._sc()`:
- 结果区画布高:`self.visual = tk.Canvas(..., height=self._sc(300))`、`kline_canvas ... height=self._sc(300)`、`spectrum_canvas ... height=self._sc(48)`。
- `_configure_styles`:`Treeview` `rowheight=self._sc(32)`;进度条 `thickness=self._sc(12)`;滚动条 `width=self._sc(11)`、`arrowsize=self._sc(11)`;Spinbox `arrowsize=self._sc(13)`。(注:`_configure_styles` 由实例调用,可用 `self._sc`。)
- 选股页 `wraplength=760` → `self._sc(760)`;说明窗 `wraplength=112` → `self._sc(112)`;进度条 `length=180` → `self._sc(180)`。
- `_refresh_table_height`(2605)如用像素高,改 `self._sc()`;若用行数×rowheight 则已随 rowheight 缩放,无需改。
- `_apply_content_band`(1698):`MAX_CONTENT_WIDTH` 传入 `compute_content_band` 时改为 `self._sc(MAX_CONTENT_WIDTH)`,`CONTENT_MARGIN` 同理 `self._sc(CONTENT_MARGIN)`——使内容带在高 DPI 下按比例加宽、留白均匀。

- [ ] **Step 4: 运行全套**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/app.py tests/test_gui_layout.py
git commit -m "feat(ui): scale fixed canvas/widget dimensions by DPI factor"
```

---

### Task 4: 修文字重叠(`_draw_empty_visual`/`_draw_visual`/`_draw_spectrum_strip`)(WS2 重叠)

**Files:**
- Modify: `src/stock_advisor/app.py`(`_draw_empty_visual` 2622、`_draw_visual` 2845、`_draw_spectrum_strip` 2493)
- (可选)Modify: `src/stock_advisor/layout.py`(抽 `stacked_text_layout` 纯函数)
- Test: `tests/test_ui_polish.py` 或 `tests/test_gui_layout.py`

**Interfaces:**
- Consumes: `self._sc`;`tkfont.Font(...).metrics("linespace")`/`.measure(text)`。
- Produces: 空态/摘要徽标与标题、光谱两行文字的坐标随字体度量下推,行距 ≥ 字体行高 → 无重叠;徽标框宽 ≥ 文案实测宽。

- [ ] **Step 1: 写失败测试(反重叠:纯布局函数)**

抽一个纯函数 `stacked_text_layout(top, line_height, gaps)` 或直接测度量关系。示例(抽 `layout.stacked_text_y`):
```python
from stock_advisor.layout import stacked_text_y
def test_stacked_text_no_overlap():
    # 给定行高 47(250% 下 11pt 实测)与起始 y,后一行 y 必须 >= 前一行 y + 行高
    ys = stacked_text_y(top=18, line_height=47, count=2)
    assert ys[1] - ys[0] >= 47
```
(若不抽纯函数,则写 GUI 测试:强制 `_ui_scale=2.5`,`_draw_empty_visual()` 后从 `visual` canvas 的 text item bbox 断言两行不重叠——`self.visual.bbox(id1)` 底 ≤ `bbox(id2)` 顶。优先抽纯函数,更稳。)

- [ ] **Step 2: 运行,确认失败**

Run: `python -m unittest tests.test_ui_polish -k stacked_text -v 2>&1 | tail`
Expected: FAIL / ImportError。

- [ ] **Step 3: 实现**

(a) 若抽纯函数,在 `layout.py` 加:
```python
def stacked_text_y(top: int, line_height: int, count: int) -> list[int]:
    """从 top 起、每行至少 line_height 间距的纵向基线序列。"""
    return [int(top) + i * int(line_height) for i in range(int(count))]
```
(b) 在 `_draw_empty_visual`/`_draw_visual`:所有硬编码坐标(徽标框 `left+18…left+166`ד`top+18…top+64`、"待分析" `(left+92, top+41)`、"今日结论" `(left+188, top+25)`、消息 `(top+51)` 等)一律外套 `self._sc(...)`;两行标题/消息的纵向位置改用**字体行高**:`lh = tkfont.Font(font=("Microsoft YaHei UI", self._sc_pt(11))).metrics("linespace")` 逐行下推(或 `stacked_text_y`),使行距 ≥ 行高;徽标框右边界取 `max(self._sc(166), x0 + font.measure(action_label) + self._sc(20))` 防溢出。
   - 注:字体仍用 pt(Tk 自动按 scaling 放大),故**坐标用 `self._sc()`**即可与放大字体对齐;`self._sc_pt` 不需要——pt 由 Tk 缩放,像素坐标由 `_sc` 缩放,两者同因子。
(c) `_draw_spectrum_strip`(2493):两行文字 `y=18`/`y=33` 改 `self._sc(18)`/按行高下推;画布高已在 Task 3 改为 `self._sc(48)`,若两行仍挤则提高到容纳 `2*行高`。

- [ ] **Step 4: 运行全套 + 真机目视(可选)**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/stock_advisor/app.py src/stock_advisor/layout.py tests/test_ui_polish.py
git commit -m "fix(ui): lay out empty-visual/spectrum text by font metrics to end overlap"
```

---

### Task 5: K线 tooltip + 余下固定尺寸收尾 + 真机自检(WS2 收尾)

**Files:**
- Modify: `src/stock_advisor/app.py`(`_on_kline_motion` 513;grep 余下裸像素)
- Test: `tests/test_gui_layout.py`

**Interfaces:**
- Consumes: `self._sc`、`tkfont.measure`。
- Produces: K线十字光标 tooltip 底框按实测字宽/行高绘制,不溢出;全屏无残留的 96-DPI 固定像素。

- [ ] **Step 1: 写失败/断言测试(tooltip 框宽≥文案实测宽)**

在 `tests/test_gui_layout.py` 增加:强制 `_ui_scale=2.5`,触发一次 `_on_kline_motion`(或直接调用其内部计算),断言底框宽度 ≥ `font.measure(text)`(而非 `7.2*len`)。若难以直接触发,抽 tooltip 框尺寸计算为纯/小函数再测。

- [ ] **Step 2: 运行,确认失败** — Run 对应用例,Expected FAIL。

- [ ] **Step 3: 实现**

- `_on_kline_motion`(513):底框宽由 `7.2 * len(text)` 改为 `font.measure(text) + self._sc(8)`,高由固定 20 改为 `font.metrics("linespace") + self._sc(6)`;所有 `top+2…top+22` 等偏移套 `self._sc()`。
- `grep -nE '\b(top|left|x0|y0)\s*[+-]\s*[0-9]{2,}' src/stock_advisor/app.py` 巡检绘制方法里余下的两位数以上裸像素偏移,凡属画布坐标者补 `self._sc()`(逐一判断,勿误伤逻辑常量)。

- [ ] **Step 4: 全套 + 语法 + 离线自检**

Run: `python -m unittest discover -s tests 2>&1 | tail -3` → `OK`。
Run: `python -m py_compile main.py build_exe.py src/stock_advisor/*.py && echo COMPILE_OK` → `COMPILE_OK`。
Run: `python main.py --self-test` → 退出码 0、`SELF_TEST_OK`。

- [ ] **Step 5: 真机目视核验(控制器执行,非子代理)**

启动 GUI,截图确认:窗口居中于工作区、四边留白均匀、尺寸合适;首屏无文字重叠/裁切;表格、光谱、K线、详情不溢出。(沿用 memory 记录的 4K@250% 截图法。)记录"整改前后"对比。

- [ ] **Step 6: 提交**

```bash
git add src/stock_advisor/app.py tests/test_gui_layout.py
git commit -m "fix(ui): size K-line tooltip by font metrics; scale remaining canvas offsets"
```

---

## Self-Review

**1. Spec 覆盖(对应 spec WS1+WS2 / P2 阶段 2-3):**
- 删除 `scale_work_area_for_tk` 误用、物理像素几何模型 → Task 2 ✓
- `ui_scale`、按 DPI 放大 min/max/margin/内容带、居中 → Task 1(纯)+ Task 2(接入)+ Task 3(内容带)✓
- 运行期几何回归测试(此前缺失的覆盖)→ Task 1(纯)+ Task 2(集成)✓
- `scale()` 铺开固定画布/行高/装饰 → Task 3 ✓
- 文字度量排布消除"待分析/今日结论"重叠、光谱重叠 → Task 4 ✓
- K线 tooltip、Treeview 行高、wraplength → Task 3(行高/wraplength)+ Task 5(tooltip)✓
- 100%/250% 两档覆盖 → Task 1 用例含两档 ✓
- 降级(DPI 感知失败→ui_scale 1.0)→ Task 1 `ui_scale` 非法/下限用例 ✓

**2. 占位符扫描:** 无 TBD;每步有确切命令与期望。绘制坐标改造给出"套 `self._sc()` + 字体度量"的具体做法与巡检 grep。

**3. 类型/名称一致性:** `ui_scale`/`compute_main_geometry`/`self._ui_scale`/`self._sc`/`_tk_scaling`/`stacked_text_y` 在定义与调用处一致;`compute_main_geometry` 复用 `compute_centered_window`(签名一致);删除 `scale_work_area_for_tk` 后同步清理 re-export 与测试导入(Task 2 Step 4)。

**风险提示(执行者注意):**
- 桩化 GUI 几何测试若因平台差异不稳,退化为只断言纯函数 `compute_main_geometry`(Task 1 已充分覆盖 bug 回归),集成测试标注为"环境相关"。
- 绘制坐标改造要**逐一判断**:只缩放画布像素坐标/尺寸,勿缩放逻辑阈值、索引、颜色等非像素常量。
