# 股市锦囊 — 决策强度内核 + 三大模块 实现计划

> **For agentic workers:** 按任务顺序逐个实现，TDD（先写失败测试，再实现）。步骤用 `- [ ]` 跟踪。
> **本仓库非 git 仓库**：各任务以「运行全量测试 `python -m unittest discover -s tests` 全绿」为检查点，替代 commit。

**Goal:** 给「股市锦囊」加入贯穿全局的 5 档决策强度内核（测量/决策分离）、科学仓位法，以及仓位计算器、可信度回测、专业 K 线三个模块，并完成更名与 A 股本土配色。

**Architecture:** `engine.measure()` 产出客观 `Measurement` → `policy.decide(level)` 产出 `Decision` → `policy.position_plan(capital)` 产出绝对仓位。改档=对缓存 Measurement 重判，不重新联网。纯逻辑全部独立单测；`app.py` 仅渲染与线程。

**Tech Stack:** Python 3.12+（开发 3.14），运行期纯标准库（tkinter/urllib/json/csv/threading），构建 PyInstaller。

## Global Constraints

- 运行期只用 Python 标准库；构建期唯一依赖 PyInstaller；不引入 Node/.NET/浏览器框架。
- 单文件 EXE `股市锦囊.exe`（onefile/windowed）+ HTML `使用说明.html`；中间产物入 `build/`、交付物入 `dist/`；写边界在项目内。
- 纯逻辑模块无网络、无 tkinter，独立可测；`data_provider` 是唯一联网处。
- 既有 139 测试保持全绿；L3「标准」档复现既有买/持/卖与分数。
- 决策强度档位：`1 稳健 / 2 稳进 / 3 标准 / 4 积极 / 5 激进`，默认 3。
- 配色：红=涨/买/积极，绿=跌/卖/谨慎。
- 立场：可解释辅助判断，不构成投资建议；接口失败明确报错，不伪造。
- 测试命令：`python -m unittest discover -s tests`；语法：`python -m py_compile main.py build_exe.py src/stock_advisor/*.py`。

---

### Task 1: 数据模型

**Files:**
- Modify: `src/stock_advisor/models.py`（追加新 dataclass 与常量）
- Test: `tests/test_models_new.py`

**Interfaces — Produces:**
- `STANDARD_LEVEL = 3`，`LEVEL_NAMES: dict[int,str]`
- `LevelSpec(level, name, t_buy:int, t_sell:int, risk_weight:float, confidence_gate:int, risk_budget:float, position_cap:float, reward_risk:float)`
- `Measurement(symbol, name, last, change_pct, factors:list[FactorScore], risk_penalty:int, base_factor_sum:int, objective_score:int, confidence:int, indicators:IndicatorSnapshot, recent_closes:list[float], reasons:list[str], risks:list[str], history_len:int, expected_move_pct:float|None)`
- `Decision(level:int, action:Action, action_label:str, policy_score:int, suggested_position:int, forecast_label:str, reasons:list[str], risks:list[str])`
- `PositionPlan(fraction, shares:int, lots:int, entry, stop_price, stop_pct, target_price, target_pct, reward_risk, cost, max_loss, max_loss_pct, note:str)`
- `BacktestStat(action:str, count:int, win_rate:float, avg_return:float)`
- `BacktestReport(level:int, horizon:int, sample_size:int, stats:dict[str,BacktestStat], buy_hold_return:float, note:str, ok:bool=True, message:str="")`
- `SpectrumCell(level:int, name:str, action:Action, is_current:bool)`

- [ ] **Step 1: 写失败测试** `tests/test_models_new.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.models import (
    STANDARD_LEVEL, LEVEL_NAMES, LevelSpec, Measurement, Decision,
    PositionPlan, BacktestStat, BacktestReport, SpectrumCell,
)


class ModelsTests(unittest.TestCase):
    def test_level_names_and_default(self):
        self.assertEqual(STANDARD_LEVEL, 3)
        self.assertEqual(LEVEL_NAMES[1], "稳健")
        self.assertEqual(LEVEL_NAMES[2], "稳进")
        self.assertEqual(LEVEL_NAMES[5], "激进")

    def test_dataclasses_construct(self):
        spec = LevelSpec(3, "标准", 25, -25, 1.0, 0, 0.01, 0.60, 2.0)
        self.assertEqual(spec.t_buy, 25)
        cell = SpectrumCell(3, "标准", "BUY", True)
        self.assertTrue(cell.is_current)
        plan = PositionPlan(0.2, 100, 1, 10.0, 9.5, 5.0, 11.0, 10.0, 2.0, 1000.0, 50.0, 0.5, "")
        self.assertEqual(plan.lots, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** `python -m unittest tests.test_models_new -v` → ImportError。
- [ ] **Step 3: 实现** 在 `models.py` 末尾追加上述常量与 `@dataclass(frozen=True)`（字段如 Interfaces 所列；`BacktestReport.stats` 默认 `field(default_factory=dict)`）。`Action` 已存在，复用。
- [ ] **Step 4: 运行通过** `python -m unittest tests.test_models_new -v` → OK。
- [ ] **Step 5: 检查点** `python -m unittest discover -s tests` → 全绿。

---

### Task 2: 决策层 — 档位表与 decide()

**Files:**
- Create: `src/stock_advisor/policy.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes: `models.Measurement`, `models.Decision`, `models.LevelSpec`
- Produces:
  - `LEVELS: dict[int, LevelSpec]`
  - `level_spec(level:int) -> LevelSpec`，`clamp_level(level:int) -> int`
  - `decide(m: Measurement, level:int=STANDARD_LEVEL) -> Decision`

档位表（与规格一致）：

| level | name | t_buy | t_sell | risk_weight | confidence_gate | risk_budget | position_cap | reward_risk |
|---|---|---|---|---|---|---|---|---|
|1|稳健|40|-15|1.6|70|0.005|0.30|2.5|
|2|稳进|33|-19|1.3|60|0.0075|0.45|2.2|
|3|标准|25|-25|1.0|0|0.01|0.60|2.0|
|4|积极|18|-33|0.8|0|0.015|0.75|1.7|
|5|激进|12|-42|0.6|0|0.02|0.90|1.5|

- [ ] **Step 1: 写失败测试** `tests/test_policy.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.models import Measurement, IndicatorSnapshot, FactorScore
from stock_advisor.symbols import normalize_symbol
from stock_advisor.policy import LEVELS, decide, level_spec, clamp_level


def make_measurement(objective_score, confidence=70, risk_penalty=0, atr=2.5, history_len=80):
    ind = IndicatorSnapshot(ma5=10, ma20=10, ma60=10, rsi14=55, macd=0.1, macd_signal=0.05,
                            macd_histogram=0.05, bollinger_position=0.6, atr_percent=atr,
                            support=9.0, resistance=11.0, five_day_win_rate=0.6,
                            max_drawdown_20=5.0, volume_ratio=1.4, intraday_position=0.6)
    base = objective_score - risk_penalty
    return Measurement(
        symbol=normalize_symbol("600519"), name="测试", last=10.0, change_pct=1.0,
        factors=[FactorScore("均线结构", base, 28, "偏多", "x")], risk_penalty=risk_penalty,
        base_factor_sum=base, objective_score=objective_score, confidence=confidence,
        indicators=ind, recent_closes=[9, 10] * 30, reasons=["r"], risks=["k"],
        history_len=history_len, expected_move_pct=atr,
    )


class PolicyTests(unittest.TestCase):
    def test_levels_complete_and_monotonic(self):
        self.assertEqual(set(LEVELS), {1, 2, 3, 4, 5})
        buys = [LEVELS[i].t_buy for i in range(1, 6)]
        sells = [LEVELS[i].t_sell for i in range(1, 6)]
        self.assertEqual(buys, sorted(buys, reverse=True))   # 买入阈值随档降
        self.assertEqual(sells, sorted(sells, reverse=True)) # 卖出阈值随档降(更易卖在保守端)

    def test_standard_reproduces_thresholds(self):
        self.assertEqual(decide(make_measurement(25), 3).action, "BUY")
        self.assertEqual(decide(make_measurement(24), 3).action, "HOLD")
        self.assertEqual(decide(make_measurement(-25), 3).action, "SELL")

    def test_aggressive_buys_more_than_conservative(self):
        m = make_measurement(20)
        self.assertEqual(decide(m, 5).action, "BUY")    # 阈值12
        self.assertEqual(decide(m, 1).action, "HOLD")   # 阈值40

    def test_confidence_gate_only_conservative(self):
        m = make_measurement(45, confidence=50)         # 分数够买，但把握仅50
        self.assertEqual(decide(m, 1).action, "HOLD")   # L1 门槛70 → 拦下
        self.assertEqual(decide(m, 3).action, "BUY")    # L3 无门槛 → 买

    def test_risk_weight_shifts_policy_score(self):
        m = make_measurement(objective_score=10, risk_penalty=-10)  # base=20
        # L5 风险权重0.6: 20 + (-10*0.6)=14 ≥12 → BUY；L1 1.6: 20-16=4 <40 → HOLD
        self.assertEqual(decide(m, 5).action, "BUY")
        self.assertEqual(decide(m, 1).action, "HOLD")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** `python -m unittest tests.test_policy -v` → ImportError。
- [ ] **Step 3: 实现** `policy.py`

```python
from __future__ import annotations

from .models import (
    Action, Decision, LevelSpec, Measurement, STANDARD_LEVEL,
)

LEVELS: dict[int, LevelSpec] = {
    1: LevelSpec(1, "稳健", 40, -15, 1.6, 70, 0.005, 0.30, 2.5),
    2: LevelSpec(2, "稳进", 33, -19, 1.3, 60, 0.0075, 0.45, 2.2),
    3: LevelSpec(3, "标准", 25, -25, 1.0, 0, 0.01, 0.60, 2.0),
    4: LevelSpec(4, "积极", 18, -33, 0.8, 0, 0.015, 0.75, 1.7),
    5: LevelSpec(5, "激进", 12, -42, 0.6, 0, 0.02, 0.90, 1.5),
}

_ACTION_LABEL = {"BUY": "买入/加仓", "SELL": "卖出/减仓", "HOLD": "继续持有/观望"}


def clamp_level(level: int) -> int:
    return max(1, min(5, int(level)))


def level_spec(level: int) -> LevelSpec:
    return LEVELS[clamp_level(level)]


def policy_score(m: Measurement, level: int) -> int:
    spec = level_spec(level)
    score = m.base_factor_sum + m.risk_penalty * spec.risk_weight
    if m.history_len < 30:
        score *= 0.75
    return max(-100, min(100, int(round(score))))


def _action(score: int, confidence: int, spec: LevelSpec) -> tuple[Action, str]:
    if score >= spec.t_buy:
        if spec.confidence_gate and confidence < spec.confidence_gate:
            return "HOLD", "信号达到买入线但把握不足，本档要求更高确认，暂观望。"
        return "BUY", ""
    if score <= spec.t_sell:
        return "SELL", ""
    return "HOLD", ""


def _forecast_label(action: Action, score: int, expected_move: float | None) -> str:
    move = f"；常态波动约±{expected_move:.2f}%" if expected_move is not None else ""
    if action == "BUY":
        strength = "强偏多" if score >= 55 else "偏多"
        return f"{strength}，适合等待回踩或放量确认后分批参与{move}"
    if action == "SELL":
        strength = "强偏空" if score <= -55 else "偏空"
        return f"{strength}，优先控制回撤，反弹不放量时降低仓位{move}"
    return f"中性震荡，等待突破压力或跌破支撑后的方向确认{move}"


def decide(m: Measurement, level: int = STANDARD_LEVEL) -> Decision:
    spec = level_spec(level)
    score = policy_score(m, level)
    action, gate_note = _action(score, m.confidence, spec)
    reasons = list(m.reasons) or ["有效信号不足，模型保持中性。"]
    risks = list(m.risks)
    if gate_note:
        risks.insert(0, gate_note)
    if action == "HOLD" and not gate_note:
        risks.append("多空证据分歧，等待方向确认比追涨杀跌更稳妥。")
    from .policy import size_fraction  # 同模块，见 Task 4
    suggested = round(size_fraction(m, level) * 100)
    return Decision(
        level=spec.level, action=action, action_label=_ACTION_LABEL[action],
        policy_score=score, suggested_position=int(suggested),
        forecast_label=_forecast_label(action, score, m.expected_move_pct),
        reasons=reasons, risks=risks,
    )
```

> 注：`decide` 调用 `size_fraction`（Task 4 同文件实现）。Task 2 先以临时 `size_fraction` 占位（`return 0.0`）让本任务测试通过，Task 4 再替换为真实实现并补测试。

- [ ] **Step 4: 运行通过** `python -m unittest tests.test_policy -v` → OK（先放占位 size_fraction）。
- [ ] **Step 5: 检查点** `python -m unittest discover -s tests` → 全绿。

---

### Task 3: 引擎重构 — measure() 与 analyze_stock 薄包装

**Files:**
- Modify: `src/stock_advisor/engine.py`
- Test: `tests/test_engine.py`（既有，必须保持全绿）；新增 `tests/test_measure.py`

**Interfaces:**
- Consumes: `policy.decide`
- Produces: `measure(quote, history) -> Measurement`；`analyze_stock(quote, history, level=STANDARD_LEVEL) -> AnalysisResult`（签名兼容，新增可选 level）

做法：把现有 `analyze_stock` 体内「算指标 + 8 因子 + 风控扣分 + 置信度 + expected_move」搬进 `measure()`，返回 `Measurement`（`factors`=8 因子；`risk_penalty`=风控扣分值；`base_factor_sum`=sum(8因子)；`objective_score`=clamp(base+penalty，含<30样本×0.75)；`confidence`=现有 `_confidence`）。`analyze_stock` 改为：

```python
def analyze_stock(quote, history, level=STANDARD_LEVEL):
    m = measure(quote, history)
    return build_analysis_result(m, decide(m, level))
```

`build_analysis_result(m, d)` 组装 `AnalysisResult`：`score=d.policy_score`、`action=d.action`、`suggested_position=d.suggested_position`、`forecast_label=d.forecast_label`、`reasons=d.reasons`、`risks=d.risks`、`factor_scores`= m.factors + （若 risk_penalty≠0）追加 `FactorScore("风控扣分", risk_penalty, 20, "谨慎", "跳空、振幅或回撤触发风险扣分。")` 后 `_dedupe_factors`，其余字段取自 m。

- [ ] **Step 1: 写失败测试** `tests/test_measure.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.engine import measure, analyze_stock
from tests.test_engine import make_quote, make_history


class MeasureTests(unittest.TestCase):
    def test_measure_is_level_independent(self):
        h = make_history(start=20, step=0.25, days=80)
        q = make_quote("600519", 41.0, 40.2, 41.2, 39.9, 40.0, volume=260000)
        m = measure(q, h)
        self.assertEqual(m.objective_score, m.base_factor_sum + m.risk_penalty
                         if m.history_len >= 30 else m.objective_score)
        self.assertGreater(len(m.factors), 0)
        self.assertIsInstance(m.confidence, int)

    def test_standard_level_matches_default(self):
        h = make_history(start=20, step=0.25, days=80)
        q = make_quote("600519", 41.0, 40.2, 41.2, 39.9, 40.0, volume=260000)
        self.assertEqual(analyze_stock(q, h).action, analyze_stock(q, h, level=3).action)
        self.assertEqual(analyze_stock(q, h, level=3).action, "BUY")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** `python -m unittest tests.test_measure -v` → ImportError(measure)。
- [ ] **Step 3: 实现** 重构 `engine.py`：新增 `measure()` 与 `build_analysis_result()`；`analyze_stock` 改薄包装；从 `.policy import decide`。保留所有 `_score_*`/指标函数不变。
- [ ] **Step 4: 运行** `python -m unittest tests.test_measure tests.test_engine -v` → 全 PASS（若 `test_engine` 对 `suggested_position` 的断言因新仓位法失败，Task 4 修复仓位后复跑；本步先保证 action/score 路径不变）。
- [ ] **Step 5: 检查点** `python -m unittest discover -s tests` → 全绿（仓位相关断言可能临时挂，记录待 Task 4）。

---

### Task 4: 仓位科学化 — size_fraction 与 position_plan

**Files:**
- Modify: `src/stock_advisor/policy.py`（替换占位 size_fraction，新增 position_plan）
- Test: `tests/test_sizing.py`

**Interfaces — Produces:**
- `size_fraction(m: Measurement, level:int) -> float`（0..cap）
- `position_plan(m: Measurement, level:int, capital:float) -> PositionPlan`

- [ ] **Step 1: 写失败测试** `tests/test_sizing.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.policy import size_fraction, position_plan
from tests.test_policy import make_measurement


class SizingTests(unittest.TestCase):
    def test_fraction_zero_for_non_buy(self):
        self.assertEqual(size_fraction(make_measurement(-30), 3), 0.0)   # SELL
        self.assertEqual(size_fraction(make_measurement(0), 3), 0.0)     # HOLD

    def test_fraction_monotonic_in_level_for_buy(self):
        m = make_measurement(40, confidence=80)
        fr = [size_fraction(m, lv) for lv in (1, 2, 3, 4, 5)]
        self.assertTrue(all(fr[i] <= fr[i + 1] + 1e-9 for i in range(4)))
        self.assertLessEqual(fr[4], 0.90)

    def test_position_plan_lot_rounding_and_loss(self):
        m = make_measurement(40, confidence=80, atr=2.5)  # last=10.0
        plan = position_plan(m, 3, capital=100000)
        self.assertEqual(plan.shares % 100, 0)
        self.assertGreater(plan.shares, 0)
        self.assertAlmostEqual(plan.max_loss, plan.shares * (plan.entry - plan.stop_price), places=2)
        self.assertGreater(plan.target_price, plan.entry)

    def test_capital_too_small_zero_shares(self):
        m = make_measurement(40, confidence=80)  # last=10 → 1手=1000元
        plan = position_plan(m, 1, capital=500)
        self.assertEqual(plan.shares, 0)
        self.assertIn("不足", plan.note)

    def test_hold_plan_has_note_no_long(self):
        plan = position_plan(make_measurement(0), 3, capital=100000)
        self.assertEqual(plan.shares, 0)
        self.assertTrue(plan.note)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** `python -m unittest tests.test_sizing -v` → 占位返回 0 → 多条 FAIL。
- [ ] **Step 3: 实现** 替换 `policy.py` 中占位，新增：

```python
import math
from .models import PositionPlan

def _stop_pct(m: Measurement) -> float:
    atr = m.indicators.atr_percent
    if atr is None or atr <= 0:
        atr = m.expected_move_pct or 3.0
    return max(2.0, min(12.0, 1.8 * atr))

def size_fraction(m: Measurement, level: int) -> float:
    spec = level_spec(level)
    score = policy_score(m, level)
    if score < spec.t_buy:               # 仅买入给多头仓位
        return 0.0
    if spec.confidence_gate and m.confidence < spec.confidence_gate:
        return 0.0
    stop = _stop_pct(m) / 100.0
    strength = max(0.4, min(1.0, abs(score) / 55.0))
    conf = max(0.5, min(1.0, m.confidence / 100.0))
    frac = (spec.risk_budget / stop) * strength * conf
    return max(0.0, min(spec.position_cap, frac))

def position_plan(m: Measurement, level: int, capital: float) -> PositionPlan:
    spec = level_spec(level)
    entry = m.last
    stop_pct = _stop_pct(m)
    stop_price = round(entry * (1 - stop_pct / 100.0), 2)
    target_pct = stop_pct * spec.reward_risk
    target_price = round(entry * (1 + target_pct / 100.0), 2)
    frac = size_fraction(m, level)
    note = ""
    if frac <= 0:
        note = "本档观望/减仓，不建议新建多头仓位。"
        shares = 0
    else:
        shares = int(capital * frac / entry // 100) * 100
        if shares <= 0:
            note = f"本金不足以买入 1 手（约 {entry * 100:.0f} 元）。"
    cost = shares * entry
    max_loss = shares * (entry - stop_price)
    return PositionPlan(
        fraction=round(frac, 4), shares=shares, lots=shares // 100, entry=entry,
        stop_price=stop_price, stop_pct=round(stop_pct, 2), target_price=target_price,
        target_pct=round(target_pct, 2), reward_risk=spec.reward_risk, cost=round(cost, 2),
        max_loss=round(max_loss, 2), max_loss_pct=round(max_loss / capital, 4) if capital > 0 else 0.0,
        note=note,
    )
```

- [ ] **Step 4: 运行** `python -m unittest tests.test_sizing tests.test_policy tests.test_engine -v` → PASS。如 `test_engine` 仍因 `suggested_position` 具体值挂，调整该断言为范围/`>0`（保持行为意图）。
- [ ] **Step 5: 检查点** `python -m unittest discover -s tests` → 全绿。

---

### Task 5: 决策强度光谱 spectrum / flip_hint

**Files:**
- Modify: `src/stock_advisor/policy.py`
- Test: `tests/test_spectrum.py`

**Interfaces — Produces:**
- `spectrum(m: Measurement, current_level:int) -> list[SpectrumCell]`（5 格）
- `flip_hint(cells: list[SpectrumCell]) -> str`

- [ ] **Step 1: 写失败测试** `tests/test_spectrum.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.policy import spectrum, flip_hint
from tests.test_policy import make_measurement


class SpectrumTests(unittest.TestCase):
    def test_five_cells_current_marked(self):
        cells = spectrum(make_measurement(20), 3)
        self.assertEqual([c.level for c in cells], [1, 2, 3, 4, 5])
        self.assertTrue(cells[2].is_current)

    def test_buy_set_upward_closed(self):
        cells = spectrum(make_measurement(20), 3)  # 阈值: L3=25,L4=18,L5=12 → 买在 L4,L5
        acts = [c.action for c in cells]
        first_buy = next((i for i, a in enumerate(acts) if a == "BUY"), None)
        self.assertIsNotNone(first_buy)
        self.assertTrue(all(a == "BUY" for a in acts[first_buy:]))

    def test_flip_hint_text(self):
        hint = flip_hint(spectrum(make_measurement(20), 3))
        self.assertTrue(isinstance(hint, str) and hint)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** → ImportError。
- [ ] **Step 3: 实现**

```python
from .models import SpectrumCell

def spectrum(m: Measurement, current_level: int) -> list[SpectrumCell]:
    cur = clamp_level(current_level)
    out = []
    for lv in range(1, 6):
        spec = LEVELS[lv]
        out.append(SpectrumCell(lv, spec.name, decide(m, lv).action, lv == cur))
    return out

def flip_hint(cells: list[SpectrumCell]) -> str:
    buys = [c for c in cells if c.action == "BUY"]
    sells = [c for c in cells if c.action == "SELL"]
    if len(buys) == 5:
        return "各档均建议买入 —— 信号较强。"
    if buys:
        return f"需到「{buys[0].name}」及以上才建议买入；更保守则观望。"
    if len(sells) == 5:
        return "各档均建议卖出/减仓 —— 风险偏高。"
    if sells:
        return f"「{sells[-1].name}」及以下偏向卖出/减仓；更激进则倾向持有。"
    return "各档均建议观望，方向尚不明朗。"
```

- [ ] **Step 4: 运行通过** → OK。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 6: 可信度回测 backtest.py

**Files:**
- Create: `src/stock_advisor/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `engine.measure`, `policy.decide`, `models.DailyBar/Quote`
- Produces: `quote_from_bar(bar, prev) -> Quote`；`backtest_signals(history, level=STANDARD_LEVEL, horizon=5, warmup=30, cost_pct=0.13) -> BacktestReport`

- [ ] **Step 1: 写失败测试** `tests/test_backtest.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.backtest import backtest_signals
from tests.test_engine import make_history


class BacktestTests(unittest.TestCase):
    def test_uptrend_buy_signals_positive(self):
        report = backtest_signals(make_history(start=20, step=0.3, days=90), level=3, horizon=5)
        self.assertGreater(report.sample_size, 0)
        buy = report.stats.get("BUY")
        self.assertIsNotNone(buy)
        self.assertGreater(buy.count, 0)
        self.assertGreater(buy.avg_return, 0)

    def test_insufficient_sample_reports_not_ok(self):
        report = backtest_signals(make_history(days=20), level=3, horizon=5, warmup=30)
        self.assertFalse(report.ok)
        self.assertTrue(report.message)

    def test_cost_reduces_returns(self):
        h = make_history(start=20, step=0.3, days=90)
        hi = backtest_signals(h, cost_pct=0.0)
        lo = backtest_signals(h, cost_pct=1.0)
        self.assertGreaterEqual(hi.stats["BUY"].avg_return, lo.stats["BUY"].avg_return)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** → ImportError。
- [ ] **Step 3: 实现** `backtest.py`

```python
from __future__ import annotations

from statistics import mean
from .engine import measure
from .policy import decide
from .models import BacktestReport, BacktestStat, DailyBar, Quote, STANDARD_LEVEL


def quote_from_bar(bar: DailyBar, prev: DailyBar | None) -> Quote:
    prev_close = prev.close if prev else bar.open
    change = (bar.close - prev_close) / prev_close * 100 if prev_close else 0.0
    return Quote(
        symbol=None, name="", last=bar.close, open=bar.open, high=bar.high, low=bar.low,
        previous_close=prev_close, volume=bar.volume, amount=bar.amount,
        turnover_rate=bar.turnover_rate, change_pct=change,
    )  # symbol 不参与测量计算


def backtest_signals(history, level=STANDARD_LEVEL, horizon=5, warmup=30, cost_pct=0.13):
    n = len(history)
    if n < warmup + horizon + 1:
        return BacktestReport(level=level, horizon=horizon, sample_size=0, stats={},
                              buy_hold_return=0.0, note="样本不足", ok=False,
                              message="历史样本不足，暂不回测（需更多交易日）。")
    rows: dict[str, list[float]] = {"BUY": [], "SELL": [], "HOLD": []}
    fwd_all: list[float] = []
    for t in range(warmup, n - horizon):
        as_of = history[:t]
        q = quote_from_bar(history[t], history[t - 1] if t > 0 else None)
        action = decide(measure(q, as_of), level).action
        fwd = (history[t + horizon].close - history[t].close) / history[t].close * 100 - cost_pct
        rows[action].append(fwd)
        fwd_all.append(fwd + cost_pct)
    stats = {}
    for action, vals in rows.items():
        if not vals:
            continue
        wins = sum(1 for v in vals if (v > 0) == (action != "SELL")) if action != "HOLD" else sum(1 for v in vals if v > 0)
        stats[action] = BacktestStat(action=action, count=len(vals),
                                     win_rate=round(wins / len(vals), 4),
                                     avg_return=round(mean(vals), 4))
    return BacktestReport(
        level=level, horizon=horizon, sample_size=sum(len(v) for v in rows.values()),
        stats=stats, buy_hold_return=round(mean(fwd_all), 4) if fwd_all else 0.0,
        note=f"近{n}日 · 持有{horizon}日 · 单边成本{cost_pct}% · 仅当日及之前数据，不预示未来",
    )
```

> `Quote.symbol` 当前为非 Optional；若构造报错，给 `quote_from_bar` 传入一个占位 `normalize_symbol("600519")`，或把 `Quote.symbol` 注解放宽。实现时按既有 `Quote` 定义选其一（优先传占位 symbol，避免改 models）。

- [ ] **Step 4: 运行通过** `python -m unittest tests.test_backtest -v` → OK。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 7: 专业 K 线几何 chart.py

**Files:**
- Create: `src/stock_advisor/chart.py`
- Test: `tests/test_chart.py`

**Interfaces — Produces:**
- `index_to_x(i:int, n:int, left:float, right:float) -> float`
- `price_to_y(price:float, lo:float, hi:float, top:float, height:float) -> float`
- `moving_average_series(closes:list[float], window:int) -> list[float|None]`
- `candle_layout(bars:list[DailyBar], left, right, top, height) -> list[dict]`（每根含 `x, body_top, body_bottom, wick_top, wick_bottom, up`）
- `price_bounds(bars) -> tuple[float,float]`

- [ ] **Step 1: 写失败测试** `tests/test_chart.py`

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.chart import index_to_x, price_to_y, moving_average_series, candle_layout, price_bounds
from tests.test_engine import make_history


class ChartTests(unittest.TestCase):
    def test_price_to_y_inverted_and_bounded(self):
        self.assertAlmostEqual(price_to_y(10, 10, 20, 0, 100), 100)  # 最低价在底部
        self.assertAlmostEqual(price_to_y(20, 10, 20, 0, 100), 0)    # 最高价在顶部

    def test_index_to_x_spreads(self):
        xs = [index_to_x(i, 5, 0, 100) for i in range(5)]
        self.assertTrue(all(xs[i] < xs[i + 1] for i in range(4)))

    def test_ma_warmup_none(self):
        s = moving_average_series([1, 2, 3, 4, 5], 3)
        self.assertEqual(s[:2], [None, None])
        self.assertAlmostEqual(s[2], 2.0)

    def test_candle_layout_orientation(self):
        bars = make_history(start=10, step=0.2, days=10)
        layout = candle_layout(bars, 0, 100, 0, 100)
        self.assertEqual(len(layout), 10)
        self.assertTrue(all("up" in c for c in layout))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败** → ImportError。
- [ ] **Step 3: 实现** `chart.py`（纯函数，无 tkinter）。`price_to_y = top + (1-(p-lo)/(hi-lo))*height`，`hi==lo` 时取中线。`candle_layout` 用 `index_to_x` 与 `price_to_y` 计算每根坐标，`up = close>=open`。
- [ ] **Step 4: 运行通过** → OK。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 8: 配色集中与翻转（红=涨/买，绿=跌/卖）

**Files:**
- Modify: `src/stock_advisor/app.py`（`_score_color`/`_action_color`/tree tags/detail tags/视觉色）
- Test: `tests/test_app_helpers.py`（补充配色断言）

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_app_helpers.py`）

```python
def test_colors_a_share_native(self):
    from stock_advisor.app import _score_color, _action_color
    self.assertEqual(_action_color("BUY"), _score_color(10))   # 买/涨同色
    self.assertNotEqual(_score_color(10), _score_color(-10))   # 涨跌异色
    # 红=涨：正分色应是暖红族
    self.assertTrue(_score_color(10).lower() in ("#c0392b", "#b4232c", "#c2261d"))
```

- [ ] **Step 2: 运行确认失败** → AssertionError（当前正分为绿）。
- [ ] **Step 3: 实现** 在 `app.py` 顶部定义命名常量 `POS_COLOR="#b4232c"`（红）、`NEG_COLOR="#167044"`（绿）、`FLAT_COLOR="#64748b"`。改：`_score_color`（>0→POS，<0→NEG）；`_action_color`（BUY→POS，SELL→NEG，HOLD 灰）；`_configure_tree_tags`（action_buy 红底红字 `#fdeef0`/`#b4232c`，action_sell 绿底绿字 `#eafaf2`/`#167044`）；detail tag `positive`→POS、`negative`→NEG；`_action_color`/摘要色随之。`_looks_positive/_looks_negative` 关键词集合不变，仅着色标签映射翻转。
- [ ] **Step 4: 运行** `python -m unittest tests.test_app_helpers -v` → PASS。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 9: 编排层回传 Measurement（支持改档重判）

**Files:**
- Modify: `src/stock_advisor/workflow.py`
- Test: `tests/test_workflow.py`（既有，保持绿；补一条 Measurement 回传断言）

做法：`AnalysisOutcome` 增 `measurement: Measurement | None`；`analyze_symbol` 内 `measure()`+`build_analysis_result(decide())`，把 measurement 一并返回。`_deep_analyze` 把 measurement 存入 `Recommendation`（`Recommendation` 增可选 `measurement` 字段于 models）。深度分析改用 measure+decide（标准档），app 后续可改档重判。

- [ ] **Step 1: 写失败测试**（追加 `tests/test_workflow.py`）

```python
def test_outcome_carries_measurement(self):
    outcome = analyze_symbol(normalize_symbol("600519"), FakeProvider())
    self.assertIsNotNone(outcome.measurement)
    self.assertGreater(len(outcome.measurement.factors), 0)
```

- [ ] **Step 2: 运行确认失败** → AttributeError。
- [ ] **Step 3: 实现** 改 `models.Recommendation` 增 `measurement: "Measurement | None" = None`；改 `AnalysisOutcome` 与 `analyze_symbol`/`_deep_analyze`。
- [ ] **Step 4: 运行** `python -m unittest tests.test_workflow -v` → PASS。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 10: 顶部决策强度滑杆 + 改档即时重判 + 配色应用 + 更名

**Files:**
- Modify: `src/stock_advisor/app.py`
- Test: `tests/test_app_helpers.py`

做法：
- `APP_TITLE = "股市锦囊"`；窗口标题、logo 提示随之。
- header 增 5 档滑杆（`tk.Scale` from_=1 to=5 或自绘；用 `ttk`/`tk.Scale` 横向，label 显示当前档名 + 该档阈值/预算摘要）。`self.level_var = tk.IntVar(value=3)`。
- 缓存：`self.measurements: dict[iid, Measurement]`；分析/选股时存入。滑杆变化 → `self._on_level_change()`：对每个缓存 measurement 重 `decide`+`size_fraction`，刷新表格行（建议/分/仓位列）、当前选中详情/光谱/计算器/可视化。**不重新联网。**
- 纯函数 `level_summary(level) -> str`（如「标准 · 买入线+25/卖出线−25 · 风险预算1%」）便于测试。

- [ ] **Step 1: 写失败测试**（追加 `tests/test_app_helpers.py`）

```python
def test_app_title_renamed(self):
    from stock_advisor.app import APP_TITLE
    self.assertEqual(APP_TITLE, "股市锦囊")

def test_level_summary(self):
    from stock_advisor.app import level_summary
    self.assertIn("标准", level_summary(3))
    self.assertIn("激进", level_summary(5))
```

- [ ] **Step 2: 运行确认失败** → ImportError/AssertionError。
- [ ] **Step 3: 实现** 上述 UI 与 `level_summary`；表格行渲染改为「按当前档」（`format_result_row` 已基于 result，重判后 result 更新即可）。新增结果表「建议仓位」列（值 `f"{result.suggested_position}%"`）。
- [ ] **Step 4: 运行** `python -m unittest tests.test_app_helpers -v` → PASS。手动冒烟：`python main.py`（可选）。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 11: 选中股新渲染 — 专业 K 线 + 光谱尺 + 计算器 + 回测

**Files:**
- Modify: `src/stock_advisor/app.py`
- Test: `tests/test_app_helpers.py`、`tests/test_ui_polish.py`

做法（渲染纯文本 builder 先抽出可测，再接 tkinter）：
- `build_position_plan_text(plan: PositionPlan, level_name:str) -> str`、`build_backtest_text(report: BacktestReport) -> str`、`build_spectrum_caption(cells) -> str`：纯函数，单测。
- 计算器：详情区下方卡，含「可用本金」`tk.Entry`（默认 100000，`self.capital_var`，会话内记忆），渲染 `position_plan(measurement, level, capital)`；本金变化即时刷新。
- 回测：选中股时对其 `recent`/history 跑 `backtest_signals(level)`（CPU 级，约 0.x 秒；可在分析线程预算或选中时同步算并缓存）。展示胜率/平均收益/基线/超额 + 诚实声明。
- K 线：用 `chart.py` 在 `self.visual` 画蜡烛（红涨绿跌）+ MA5/MA10/MA20 + 量副图 + 支撑压力 + 回测买点（蓝三角）。替换 `_draw_sparkline` 调用。
- 光谱尺：在可视化区上方画 5 格（红买/灰观望/绿卖），高亮当前档 + `flip_hint` 文案。

- [ ] **Step 1: 写失败测试**

```python
def test_position_plan_text(self):
    from stock_advisor.app import build_position_plan_text
    from stock_advisor.policy import position_plan
    from tests.test_policy import make_measurement
    txt = build_position_plan_text(position_plan(make_measurement(40, confidence=80), 3, 100000), "标准")
    self.assertIn("止损", txt)
    self.assertIn("最大亏损", txt)

def test_backtest_text(self):
    from stock_advisor.app import build_backtest_text
    from stock_advisor.backtest import backtest_signals
    from tests.test_engine import make_history
    txt = build_backtest_text(backtest_signals(make_history(start=20, step=0.3, days=90), 3))
    self.assertIn("胜率", txt)
    self.assertIn("不预示未来", txt)
```

- [ ] **Step 2: 运行确认失败** → ImportError。
- [ ] **Step 3: 实现** builder + tkinter 渲染（K线/光谱/计算器/回测）。
- [ ] **Step 4: 运行** `python -m unittest tests.test_app_helpers tests.test_ui_polish -v` → PASS。
- [ ] **Step 5: 检查点** → 全绿。

---

### Task 12: 更名收尾 + 说明书 + 自测 + 打包验证

**Files:**
- Modify: `build_exe.py`（`股市锦囊.exe`、`使用说明.html`）、`src/stock_advisor/manual.py`（更名 + 新章节）、`main.py`（自测覆盖新管线 + 更名串）、`README.md`、`AGENTS.md`
- Test: `tests/test_build_config.py`、`tests/test_manual.py`、`tests/test_main.py`

- [ ] **Step 1: 写失败测试** 更新 `test_build_config.py` 断言 EXE 名含「股市锦囊」、HTML 名为「使用说明」；`test_manual.py` 断言说明书含「决策强度」「仓位」「回测」章节与新名。
- [ ] **Step 2: 运行确认失败** → AssertionError。
- [ ] **Step 3: 实现** 改 `build_exe.py` 输出名与 HTML；`manual.py` 增「决策强度怎么用」「仓位/风控计算器」「可信度回测」「配色说明（红涨绿跌）」章节并更名；`main.py` `_self_test` 增：对样例跑 `measure`→`decide`（L1 与 L5 行动可不同）、`position_plan`、`backtest_signals`，打印含 level 的 `SELF_TEST_OK`；README/AGENTS 全量更名 `A股策略助手`→`股市锦囊` 与交付物名。
- [ ] **Step 4: 运行** `python -m unittest discover -s tests` 全绿；`python -m py_compile main.py build_exe.py src/stock_advisor/*.py`；`python main.py --self-test` 打印 `SELF_TEST_OK`。
- [ ] **Step 5: 打包验证** `python build_exe.py` → `dist\股市锦囊.exe --self-test` 退出码 0、打印 `SELF_TEST_OK`；确认 `dist\使用说明.html` 生成。GUI 冒烟截图（按用户记忆 `stock-adviser-gui-verification` 的方式核验 4K@250%）。

---

## Self-Review（对照规格）

- **覆盖**：决策强度内核(T2/T3)、仓位科学化(T4)、光谱(T5)、回测(T6)、K线(T7)、配色(T8)、贯穿两页(T9/T10)、三模块渲染(T11)、更名/说明书/打包(T12) —— 规格各节均有对应任务。
- **回归**：T3 保证 L3 行为不变；T4 仅调整仓位数值断言。
- **类型一致**：`Measurement`/`Decision`/`PositionPlan`/`BacktestReport`/`SpectrumCell` 在 T1 定义，后续任务签名引用一致；`decide`/`size_fraction`/`position_plan`/`spectrum`/`flip_hint` 命名贯穿统一。
- **无占位**：核心算法均给出真实代码；UI 任务给出可测 builder 真实代码 + 精确接线说明。
