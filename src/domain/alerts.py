from __future__ import annotations

from .models import AlertRule
from .numeric import finite_float as _finite_float

FIELD_LABELS = {"price": "价格", "change_pct": "涨跌幅", "score": "综合分"}
# 字段下拉展示 FIELD_LABELS 的中文值；选中后需要映射回这里的键写入 AlertRule.field
# （告警求值/展示逻辑均按键索引，不受下拉展示文案影响）。
FIELD_KEYS_BY_LABEL = {label: key for key, label in FIELD_LABELS.items()}
OPS = (">=", "<=")


def _field_value(field: str, result) -> float | None:
    if field == "price":
        return result.last
    if field == "change_pct":
        return result.change_pct
    if field == "score":
        return float(result.score)
    return None


def evaluate_rule(rule: AlertRule, result) -> bool:
    if result is None:
        return False
    value = _finite_float(_field_value(rule.field, result))
    threshold = _finite_float(rule.threshold)
    if value is None or threshold is None:
        return False
    if rule.op == ">=":
        return value >= threshold
    if rule.op == "<=":
        return value <= threshold
    return False


def rule_key(rule: AlertRule) -> tuple:
    return (rule.code, rule.field, rule.op, rule.threshold)


def rule_summary(rule: AlertRule) -> str:
    from .symbols import normalize_symbol

    try:
        display = normalize_symbol(rule.code).display
    except ValueError:
        display = rule.code
    label = FIELD_LABELS.get(rule.field, rule.field)
    suffix = "%" if rule.field == "change_pct" else ""
    return f"{display} {label} {rule.op} {rule.threshold:g}{suffix}"


def check_rules(rules, results_by_code, fired) -> tuple[list, set]:
    """边沿触发（纯函数）：返回（本次新触发规则列表，更新后的 fired 键集合）。

    条件为真且键不在 fired → 触发并入集；条件为假或规则被禁用 → 从集合移除（复位，可再次触发）；
    缺少该 code 的结果 → 跳过、不改状态。
    """
    new_fired = set(fired)
    newly: list = []
    for rule in rules:
        key = rule_key(rule)
        if not rule.enabled:
            new_fired.discard(key)
            continue
        result = results_by_code.get(rule.code)
        if result is None:
            continue
        if evaluate_rule(rule, result):
            if key not in new_fired:
                new_fired.add(key)
                newly.append(rule)
        else:
            new_fired.discard(key)
    return newly, new_fired
