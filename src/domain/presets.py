from __future__ import annotations

import math
from dataclasses import replace

from .formatting import _format_number
from .models import FilterCriteria, ScreenPreset, TunableParam

_YI = 1.0e8  # 一亿元


def _top_n(default: int = 20) -> TunableParam:
    return TunableParam(
        key="top_n",
        label="推荐数量",
        kind="int",
        default=float(default),
        minimum=5,
        maximum=30,
        unit="只",
        help="筛选后保留并深度分析的股票数量（5~30 只）。",
    )


PRESETS: tuple[ScreenPreset, ...] = (
    ScreenPreset(
        key="momentum_strong",
        name="强势动量",
        objective="momentum",
        description="今日温和上涨、量能配合、中期趋势向上的强势股，回避过热涨停板。",
        criteria=FilterCriteria(
            change_pct_min=2.0,
            change_pct_max=7.0,
            volume_ratio_min=1.2,
            amount_min=1.0 * _YI,
            change_60d_min=0.0,
            exclude_st=True,
        ),
        tunables=(
            TunableParam(
                "change_pct_min",
                "今日涨幅下限",
                "float",
                2.0,
                0.0,
                10.0,
                "%",
                "只看涨幅高于此值的股票。",
            ),
            TunableParam(
                "volume_ratio_min",
                "量比下限",
                "float",
                1.2,
                0.5,
                5.0,
                "倍",
                "量比越高代表成交越活跃。",
            ),
            TunableParam(
                "amount_min",
                "成交额下限",
                "float",
                1.0,
                0.0,
                50.0,
                "亿",
                "过滤流动性过低的股票。",
                scale=_YI,
            ),
            _top_n(),
        ),
    ),
    ScreenPreset(
        key="breakout_volume",
        name="放量突破",
        objective="breakout",
        description="放量上攻、换手活跃的突破型品种，量比要求更高。",
        criteria=FilterCriteria(
            change_pct_min=1.0,
            change_pct_max=9.0,
            volume_ratio_min=1.8,
            turnover_min=3.0,
            turnover_max=25.0,
            amount_min=2.0 * _YI,
            exclude_st=True,
        ),
        tunables=(
            TunableParam(
                "volume_ratio_min",
                "量比下限",
                "float",
                1.8,
                1.0,
                6.0,
                "倍",
                "突破通常伴随明显放量。",
            ),
            TunableParam(
                "change_pct_min",
                "今日涨幅下限",
                "float",
                1.0,
                -2.0,
                9.0,
                "%",
                "突破当日通常已转涨。",
            ),
            TunableParam(
                "amount_min",
                "成交额下限",
                "float",
                2.0,
                0.0,
                80.0,
                "亿",
                "突破需要资金承接。",
                scale=_YI,
            ),
            _top_n(),
        ),
    ),
    ScreenPreset(
        key="rebound_oversold",
        name="超跌反弹",
        objective="rebound",
        description="中期超跌但今日开始企稳的品种，寻找修复机会。",
        criteria=FilterCriteria(
            change_pct_min=-3.0,
            change_60d_max=-15.0,
            change_ytd_max=0.0,
            amount_min=1.0 * _YI,
            exclude_st=True,
        ),
        tunables=(
            TunableParam(
                "change_60d_max",
                "60日跌幅上限",
                "float",
                -15.0,
                -60.0,
                0.0,
                "%",
                "数值越低代表要求跌得越深。",
            ),
            TunableParam(
                "change_pct_min",
                "今日企稳下限",
                "float",
                -3.0,
                -8.0,
                3.0,
                "%",
                "今日跌幅不超过此值，避免继续杀跌。",
            ),
            TunableParam(
                "amount_min",
                "成交额下限",
                "float",
                1.0,
                0.0,
                50.0,
                "亿",
                "保证一定的流动性。",
                scale=_YI,
            ),
            _top_n(),
        ),
    ),
    ScreenPreset(
        key="value_blue",
        name="低估值蓝筹",
        objective="value",
        description="低市盈率、低市净率、较大市值的稳健品种。",
        criteria=FilterCriteria(
            pe_min=0.0,
            pe_max=20.0,
            pb_min=0.5,
            pb_max=3.0,
            total_cap_min=200.0 * _YI,
            amount_min=1.0 * _YI,
            exclude_st=True,
        ),
        tunables=(
            TunableParam(
                "pe_max", "市盈率上限", "float", 20.0, 5.0, 60.0, "倍", "数值越低估值越便宜。"
            ),
            TunableParam(
                "pb_max", "市净率上限", "float", 3.0, 1.0, 10.0, "倍", "数值越低相对净资产越便宜。"
            ),
            TunableParam(
                "total_cap_min",
                "总市值下限",
                "float",
                200.0,
                0.0,
                5000.0,
                "亿",
                "偏好较大市值的蓝筹。",
                scale=_YI,
            ),
            _top_n(),
        ),
    ),
    ScreenPreset(
        key="activity_turnover",
        name="高换手活跃",
        objective="activity",
        description="换手率高、成交活跃、价格适中的高人气品种。",
        criteria=FilterCriteria(
            turnover_min=5.0,
            turnover_max=30.0,
            volume_ratio_min=1.5,
            price_min=3.0,
            price_max=60.0,
            amount_min=1.0 * _YI,
            exclude_st=True,
        ),
        tunables=(
            TunableParam(
                "turnover_min",
                "换手率下限",
                "float",
                5.0,
                1.0,
                20.0,
                "%",
                "换手越高代表交投越活跃。",
            ),
            TunableParam(
                "turnover_max", "换手率上限", "float", 30.0, 10.0, 60.0, "%", "上限避免过度投机。"
            ),
            TunableParam(
                "volume_ratio_min", "量比下限", "float", 1.5, 0.8, 5.0, "倍", "活跃通常伴随放量。"
            ),
            _top_n(),
        ),
    ),
    ScreenPreset(
        key="steady_lowvol",
        name="稳健低波动",
        objective="balanced",
        description="振幅小、换手温和、市值较大、估值合理的稳健品种。",
        criteria=FilterCriteria(
            amplitude_max=4.0,
            turnover_min=1.0,
            turnover_max=8.0,
            total_cap_min=100.0 * _YI,
            pe_min=0.0,
            pe_max=30.0,
            amount_min=1.0 * _YI,
            exclude_st=True,
        ),
        tunables=(
            TunableParam(
                "amplitude_max", "振幅上限", "float", 4.0, 1.0, 10.0, "%", "数值越低代表波动越小。"
            ),
            TunableParam(
                "total_cap_min",
                "总市值下限",
                "float",
                100.0,
                0.0,
                5000.0,
                "亿",
                "偏好较大市值。",
                scale=_YI,
            ),
            TunableParam(
                "pe_max", "市盈率上限", "float", 30.0, 5.0, 80.0, "倍", "排除估值过高的品种。"
            ),
            _top_n(),
        ),
    ),
)

_PRESET_BY_KEY = {preset.key: preset for preset in PRESETS}


def get_preset(key: str) -> ScreenPreset:
    return _PRESET_BY_KEY[key]


def default_values(preset: ScreenPreset) -> dict[str, float]:
    return {param.key: param.default for param in preset.tunables}


def apply_tunables(preset: ScreenPreset, values: dict[str, float]) -> tuple[FilterCriteria, int]:
    """把用户微调的关键参数叠加到预设条件上，返回 (有效条件, TopN)。"""
    valid = {param.key: param for param in preset.tunables}
    overrides: dict[str, float] = {}
    top_n = preset.default_top_n
    for key, raw in values.items():
        param = valid.get(key)
        if param is None:
            continue
        number = _finite_number(raw)
        if number is None:
            continue
        number = max(param.minimum, min(param.maximum, number))
        if key == "top_n":
            top_n = int(round(number))
            continue
        overrides[key] = number * param.scale
    criteria = replace(preset.criteria, **overrides) if overrides else preset.criteria
    _check_crossed_bounds(criteria, valid)
    return criteria, max(1, top_n)


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


# FilterCriteria 里每一对共享同一指标的 (下限字段, 上限字段)。amount_min 没有对应的
# amount_max，故不在此列。只要其中一侧在某预设里被暴露为可调项，用户就可能把它调到
# 越过另一侧（无论另一侧是可调项还是预设写死的固定条件），从而让 screener._in_range
# 恒为假、筛选结果恒空——这正是本函数要拦截的场景。
_BOUND_PAIRS: tuple[tuple[str, str], ...] = (
    ("price_min", "price_max"),
    ("change_pct_min", "change_pct_max"),
    ("amplitude_min", "amplitude_max"),
    ("turnover_min", "turnover_max"),
    ("volume_ratio_min", "volume_ratio_max"),
    ("total_cap_min", "total_cap_max"),
    ("float_cap_min", "float_cap_max"),
    ("pe_min", "pe_max"),
    ("pb_min", "pb_max"),
    ("change_60d_min", "change_60d_max"),
    ("change_ytd_min", "change_ytd_max"),
)


def _check_crossed_bounds(criteria: FilterCriteria, valid: dict[str, TunableParam]) -> None:
    """校验每组同指标的下限/上限没有交叉；下限>上限时抛出指名该指标的 ValueError。

    只检查至少一侧是当前预设可调项的组合：两侧都固定的边界属于预设自身数据，
    用户无法把它调到交叉，不属于本次要拦截的运行时问题。
    """
    for min_key, max_key in _BOUND_PAIRS:
        min_param = valid.get(min_key)
        max_param = valid.get(max_key)
        if min_param is None and max_param is None:
            continue
        low = getattr(criteria, min_key)
        high = getattr(criteria, max_key)
        if low is None or high is None or low <= high:
            continue
        param = min_param or max_param
        assert param is not None  # for type-checkers；上面已排除两者皆 None
        lo = _format_number(low / param.scale)
        hi = _format_number(high / param.scale)
        raise ValueError(f"『{_pair_label(param)}』下限 {lo} 高于上限 {hi}，请调低下限或调高上限。")


def _pair_label(param: TunableParam) -> str:
    """从可调项标签推导该指标本身的名字：去掉『下限/上限』方向后缀，避免消息读起来
    像“『涨幅下限』下限 10 高于上限 7”这种方向词重复；单位沿用页面上的『标签（单位）』写法。"""
    label = param.label
    for suffix in ("下限", "上限"):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
            break
    return f"{label}（{param.unit}）" if param.unit else label
