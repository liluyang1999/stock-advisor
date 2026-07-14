from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Action = Literal["BUY", "SELL", "HOLD"]

# 免责声明核心句——单一权威来源。policy.py 每条决策 risks 末尾追加的免责句、theme.py 全文
# 页脚免责声明，措辞均以此为准（避免各写各的、逐渐漂移）。theme.py 为保持自身"仅依赖标准库"
# 的叶子模块约定，不 import 本模块，改为字面量对齐同一核心句；一致性由
# tests/test_policy.py::DisclaimerConsistencyTests 兜底校验。
CORE_DISCLAIMER = "模型仅供研究和辅助决策，不构成投资建议。"


@dataclass(frozen=True)
class StockSymbol:
    raw: str
    code: str
    exchange: str
    prefix: str
    secid: str

    @property
    def normalized(self) -> str:
        return f"{self.prefix}{self.code}"

    @property
    def display(self) -> str:
        return f"{self.prefix.upper()}.{self.code}"


@dataclass(frozen=True)
class Quote:
    symbol: StockSymbol
    name: str
    last: float
    open: float
    high: float
    low: float
    previous_close: float
    volume: int
    amount: float
    turnover_rate: float
    change_pct: float
    timestamp: str = ""


@dataclass(frozen=True)
class DailyBar:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: int
    amount: float
    pct_change: float
    turnover_rate: float


@dataclass(frozen=True)
class IndicatorSnapshot:
    ma5: float | None
    ma20: float | None
    ma60: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    bollinger_position: float | None
    atr_percent: float | None
    support: float | None
    resistance: float | None
    five_day_win_rate: float | None
    max_drawdown_20: float | None
    volume_ratio: float | None
    intraday_position: float | None


@dataclass(frozen=True)
class FactorScore:
    name: str
    score: int
    max_abs_score: int
    verdict: str
    detail: str


@dataclass(frozen=True)
class MarketSnapshot:
    """全市场批量行情快照中的单只股票（东方财富 clist 字段）。缺失字段记为 None。"""

    code: str
    market_id: str  # "1"=沪, "0"=深/北（东方财富 f13）
    name: str
    price: float
    change_pct: float
    change: float
    volume: int
    amount: float
    amplitude: float
    turnover_rate: float
    pe_ttm: float | None  # 可为负（亏损）
    volume_ratio: float | None
    total_cap: float | None
    float_cap: float | None
    speed: float | None
    pb: float | None
    change_60d: float | None
    change_ytd: float | None

    @property
    def is_st(self) -> bool:
        upper = self.name.upper()
        return "ST" in upper or "退" in self.name


@dataclass(frozen=True)
class FilterCriteria:
    """选股硬性范围。所有数值区间为开区间端点，None 表示该端不限制。"""

    boards: frozenset[str] = frozenset()  # 空集表示不限板块
    exclude_st: bool = True
    exclude_loss: bool = False  # 剔除负/零市盈率（亏损）
    price_min: float | None = None
    price_max: float | None = None
    change_pct_min: float | None = None
    change_pct_max: float | None = None
    amplitude_min: float | None = None
    amplitude_max: float | None = None
    turnover_min: float | None = None
    turnover_max: float | None = None
    volume_ratio_min: float | None = None
    volume_ratio_max: float | None = None
    amount_min: float | None = None  # 成交额下限（元）
    total_cap_min: float | None = None
    total_cap_max: float | None = None
    float_cap_min: float | None = None
    float_cap_max: float | None = None
    pe_min: float | None = None
    pe_max: float | None = None
    pb_min: float | None = None
    pb_max: float | None = None
    change_60d_min: float | None = None
    change_60d_max: float | None = None
    change_ytd_min: float | None = None
    change_ytd_max: float | None = None


@dataclass(frozen=True)
class TunableParam:
    """预设里暴露给用户微调的关键参数。key 对应 FilterCriteria 字段或 'top_n'。

    scale：用户输入值到 FilterCriteria 字段值的换算系数（如成交额/市值以「亿」展示，
    scale=1e8 即把用户输入的「亿」换算成「元」写入条件）。
    """

    key: str
    label: str
    kind: str  # "float" | "int"
    default: float
    minimum: float
    maximum: float
    unit: str = ""
    help: str = ""
    scale: float = 1.0


@dataclass(frozen=True)
class ScreenPreset:
    key: str
    name: str
    objective: str  # 排序目标
    description: str
    criteria: FilterCriteria
    tunables: tuple[TunableParam, ...] = ()
    default_top_n: int = 20
    deep_analyze: bool = True


@dataclass(frozen=True)
class Recommendation:
    rank: int
    snapshot: MarketSnapshot
    screen_score: float
    board: str
    result: AnalysisResult | None = None  # 深度分析结果（可选）
    measurement: Measurement | None = None  # 客观测量（供改档即时重判）
    error: str = ""  # 深度分析失败说明


@dataclass(frozen=True)
class AnalysisResult:
    symbol: StockSymbol
    name: str
    action: Action
    action_label: str
    score: int
    confidence: int
    last: float
    change_pct: float
    suggested_position: int
    forecast_label: str
    expected_move_pct: float | None
    indicators: IndicatorSnapshot
    factor_scores: list[FactorScore] = field(default_factory=list)
    recent_closes: list[float] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


# ---- 决策强度（测量/决策分离）相关结构 ----

STANDARD_LEVEL = 3
LEVEL_NAMES: dict[int, str] = {1: "稳健", 2: "稳进", 3: "标准", 4: "积极", 5: "激进"}


@dataclass(frozen=True)
class LevelSpec:
    """单个决策强度档位的策略参数（阈值/权重/门槛/仓位预算）。"""

    level: int
    name: str
    t_buy: int  # 买入阈值（policy_score >= t_buy）
    t_sell: int  # 卖出阈值（policy_score <= t_sell，负数）
    risk_weight: float  # 风控扣分权重
    confidence_gate: int  # 买入置信门槛，0 表示不设门槛
    risk_budget: float  # 单笔风险预算（占本金比例，如 0.01）
    position_cap: float  # 仓位上限（占本金比例，如 0.60）
    reward_risk: float  # 目标盈亏比


@dataclass(frozen=True)
class Measurement:
    """对市场的客观测量，与决策档位无关。"""

    symbol: StockSymbol
    name: str
    last: float
    change_pct: float
    factors: list[FactorScore]  # 8 个测量因子（不含风控扣分）
    risk_penalty: int  # 风控扣分（≤0），供决策层按档加权
    base_factor_sum: int  # 8 因子之和（不含风控扣分）
    objective_score: int  # = clamp(base + penalty)，等于既有综合分
    confidence: int  # 客观置信度
    indicators: IndicatorSnapshot
    recent_closes: list[float]
    reasons: list[str]
    risks: list[str]
    history_len: int
    expected_move_pct: float | None


@dataclass(frozen=True)
class Decision:
    """某一档位下，对一次 Measurement 的决策输出。"""

    level: int
    action: Action
    action_label: str
    policy_score: int
    suggested_position: int  # 投入比例百分数 0..100
    forecast_label: str
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PositionPlan:
    """结合本金的绝对仓位/风控计划。"""

    fraction: float
    shares: int
    lots: int
    entry: float
    stop_price: float
    stop_pct: float
    target_price: float
    target_pct: float
    reward_risk: float
    cost: float
    max_loss: float
    max_loss_pct: float
    note: str = ""


@dataclass(frozen=True)
class BacktestStat:
    action: Action
    count: int
    win_rate: float
    avg_return: float


@dataclass(frozen=True)
class BacktestReport:
    level: int
    horizon: int
    sample_size: int
    buy_hold_return: float
    note: str
    stats: dict[str, BacktestStat] = field(default_factory=dict)
    ok: bool = True
    message: str = ""


@dataclass(frozen=True)
class SpectrumCell:
    level: int
    name: str
    action: Action
    is_current: bool


@dataclass(frozen=True)
class FundFlow:
    """个股资金流：主力净流入净额（元）。"""

    today_main: float  # 今日主力净额
    main_5d: float  # 近5日主力净额累计
    recent: list[tuple[str, float]] = field(default_factory=list)  # [(日期, 主力净额)]


# ---- 二期：自选股/持仓、持久化、横向对比 ----


@dataclass(frozen=True)
class WatchItem:
    """一条自选/持仓：code 为规范化形式（如 "sh600519"）；cost/shares 可选。"""

    code: str
    cost: float | None = None  # 持仓成本价（None 表示仅自选未持仓）
    shares: int | None = None  # 持仓股数（可选）


@dataclass(frozen=True)
class AlertRule:
    """条件预警规则：某股的某字段越过阈值。"""

    code: str  # 规范化形式，如 "sh600519"
    field: str  # "price" | "change_pct" | "score"
    op: str  # ">=" | "<="
    threshold: float
    enabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    """跨会话持久化的用户配置。"""

    watchlist: tuple[WatchItem, ...] = ()
    capital: float = 100000.0
    level: int = 3
    preset: str = ""  # 空表示用 PRESETS[0]
    alerts: tuple[AlertRule, ...] = ()


@dataclass(frozen=True)
class ComparisonRow:
    code: str
    name: str
    last: float | None
    change_pct: float | None
    score: int
    confidence: int
    risk: str
    position: int
    level_hint: str
    action: Action = "HOLD"
    cost: float | None = None
    pl_pct: float | None = None
    pl_amount: float | None = None
