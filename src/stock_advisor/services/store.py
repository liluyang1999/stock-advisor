from __future__ import annotations

import json
import math
import os
import tempfile
from decimal import Decimal
from pathlib import Path

from ..domain import money
from ..domain.alerts import FIELD_LABELS, OPS
from ..domain.models import STANDARD_LEVEL, AlertRule, AppConfig, WatchItem
from ..domain.symbols import normalize_symbol

_MAX_WATCH = 100
_MAX_ALERTS = 100
_APP_DIR_NAME = "股市锦囊"
_CONFIG_FILENAME = "config.json"


def config_path() -> Path:
    """用户配置文件路径：优先环境变量（供测试），否则 %APPDATA%\\股市锦囊\\config.json。"""
    override = os.environ.get("STOCK_ADVISOR_CONFIG")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / _APP_DIR_NAME / _CONFIG_FILENAME


def _valid_preset(preset: str) -> str:
    from ..domain.presets import PRESETS

    return preset if preset in {p.key for p in PRESETS} else ""


def _positive_or_none(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number if number > 0 else None


def _positive_int_or_none(value: object) -> int | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    if not math.isfinite(number):
        return None
    if not number.is_integer():
        return None
    integer = int(number)
    return integer if integer > 0 else None


def _bounded_level(value: object) -> int:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return STANDARD_LEVEL
    if not math.isfinite(number):
        return STANDARD_LEVEL
    return max(1, min(5, int(number)))


def _bool_or_default(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0 if math.isfinite(float(value)) else default
    return default


def _parse_item(raw: object) -> WatchItem | None:
    if isinstance(raw, str):
        code_raw: object = raw
        cost = shares = None
    elif isinstance(raw, dict):
        code_raw = raw.get("code", "")
        cost = money.positive_money(raw.get("cost"))
        shares = _positive_int_or_none(raw.get("shares"))
    else:
        return None
    try:
        symbol = normalize_symbol(str(code_raw))
    except ValueError:
        return None
    return WatchItem(code=symbol.normalized, cost=cost, shares=shares)


def parse_config(data: object) -> AppConfig:
    """把（可能脏的）配置字典解析为合法 AppConfig；纯函数、鲁棒。"""
    if not isinstance(data, dict):
        return AppConfig()

    level = _bounded_level(data.get("level", STANDARD_LEVEL))

    capital = money.parse_money(data.get("capital")) or Decimal("100000.00")
    if capital <= 0:
        capital = Decimal("100000.00")

    items: list[WatchItem] = []
    seen: set[str] = set()
    raw_list = data.get("watchlist")
    if isinstance(raw_list, list):
        for raw in raw_list:
            item = _parse_item(raw)
            if item is None or item.code in seen:
                continue
            seen.add(item.code)
            items.append(item)
            if len(items) >= _MAX_WATCH:
                break

    preset = data.get("preset", "")
    preset = _valid_preset(preset) if isinstance(preset, str) else ""

    alerts: list[AlertRule] = []
    raw_alerts = data.get("alerts")
    if isinstance(raw_alerts, list):
        for raw in raw_alerts:
            alert = _parse_alert(raw)
            if alert is None:
                continue
            alerts.append(alert)
            if len(alerts) >= _MAX_ALERTS:
                break

    return AppConfig(
        watchlist=tuple(items), capital=capital, level=level, preset=preset, alerts=tuple(alerts)
    )


def _parse_alert(raw: object) -> AlertRule | None:
    if not isinstance(raw, dict):
        return None
    field = raw.get("field")
    op = raw.get("op")
    if field not in FIELD_LABELS or op not in OPS:
        return None
    try:
        threshold = float(raw.get("threshold"))  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    if not math.isfinite(threshold):
        return None
    try:
        symbol = normalize_symbol(str(raw.get("code", "")))
    except ValueError:
        return None
    return AlertRule(
        code=symbol.normalized,
        field=field,
        op=op,
        threshold=threshold,
        enabled=_bool_or_default(raw.get("enabled", True)),
    )


def config_to_dict(cfg: AppConfig) -> dict:
    watchlist: list[dict] = []
    seen: set[str] = set()
    for raw in cfg.watchlist:
        item = _parse_item({"code": raw.code, "cost": raw.cost, "shares": raw.shares})
        if item is None or item.code in seen:
            continue
        seen.add(item.code)
        cost_text = str(item.cost) if item.cost is not None else None
        watchlist.append({"code": item.code, "cost": cost_text, "shares": item.shares})
        if len(watchlist) >= _MAX_WATCH:
            break

    alerts: list[dict] = []
    for raw in cfg.alerts:
        alert = _parse_alert(
            {
                "code": raw.code,
                "field": raw.field,
                "op": raw.op,
                "threshold": raw.threshold,
                "enabled": raw.enabled,
            }
        )
        if alert is None:
            continue
        alerts.append(
            {
                "code": alert.code,
                "field": alert.field,
                "op": alert.op,
                "threshold": alert.threshold,
                "enabled": alert.enabled,
            }
        )
        if len(alerts) >= _MAX_ALERTS:
            break

    return {
        "watchlist": watchlist,
        "capital": str(cfg.capital),
        "level": _bounded_level(cfg.level),
        "preset": _valid_preset(cfg.preset) if isinstance(cfg.preset, str) else "",
        "alerts": alerts,
    }


def load_config(path: Path | None = None) -> AppConfig:
    """读取配置；文件缺失/损坏/不可读都回退默认，绝不抛出。"""
    target = Path(path) if path is not None else config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return AppConfig()
    return parse_config(data)


def save_config(path: Path | None, cfg: AppConfig) -> bool:
    """原子写配置（临时文件 + os.replace）；失败返回 False、绝不抛出。"""
    target = Path(path) if path is not None else config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(config_to_dict(cfg), ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".cfg", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        return False
