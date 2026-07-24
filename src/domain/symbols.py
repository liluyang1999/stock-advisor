from __future__ import annotations

import re

from .models import StockSymbol

_SEPARATORS = re.compile(r"[\s,;，；]+")
_PREFIXED = re.compile(r"^(sh|sz|bj)[._-]?(\d{6})$", re.IGNORECASE)


def normalize_symbol(value: str) -> StockSymbol:
    raw = value.strip()
    compact = raw.replace(" ", "").lower()
    prefixed = _PREFIXED.match(compact)

    if prefixed:
        prefix, code = prefixed.group(1).lower(), prefixed.group(2)
    else:
        if not re.fullmatch(r"\d{6}", compact):
            raise ValueError(f"股票代码必须是6位数字，或带 SH/SZ/BJ 前缀：{value!r}")
        code = compact
        prefix = _infer_prefix(code)

    market_id, exchange = _market_for_prefix(prefix)
    return StockSymbol(
        raw=raw, code=code, exchange=exchange, prefix=prefix, secid=f"{market_id}.{code}"
    )


def symbol_from_market(code: str, market_id: object) -> StockSymbol:
    """从权威市场号（东方财富 f13: 1=沪, 0=深/北）直接构造代码，secid 不靠推断。"""
    code = str(code).strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError(f"股票代码必须是6位数字：{code!r}")
    market = str(market_id).strip()
    if market not in {"0", "1"}:
        raise ValueError(f"不支持的市场号：{market_id!r}")
    if market == "1":
        prefix, exchange = "sh", "上海证券交易所"
    elif code.startswith(("92", "8", "4")):
        prefix, exchange = "bj", "北京证券交易所"
    else:
        prefix, exchange = "sz", "深圳证券交易所"
    return StockSymbol(
        raw=code, code=code, exchange=exchange, prefix=prefix, secid=f"{market}.{code}"
    )


def parse_user_symbols(text: str, max_count: int = 30) -> list[StockSymbol]:
    symbols: list[StockSymbol] = []
    seen: set[str] = set()
    for token in _SEPARATORS.split(text.strip()):
        if not token:
            continue
        symbol = normalize_symbol(token)
        if symbol.normalized in seen:
            continue
        seen.add(symbol.normalized)
        symbols.append(symbol)
        if len(symbols) > max_count:
            raise ValueError(f"单次最多分析 {max_count} 只股票，请减少输入数量后重试。")
    if not symbols:
        raise ValueError("请输入至少一个股票代码。")
    return symbols


def _infer_prefix(code: str) -> str:
    if code.startswith("92"):  # 北交所新代码段（920xxx），需先于 9 开头的沪市判断
        return "bj"
    if code.startswith(("6", "9")):  # 沪市主板 / 沪市B股（900xxx）
        return "sh"
    if code.startswith(("4", "8")):  # 北交所老代码段
        return "bj"
    if code.startswith(("0", "2", "3")):  # 深市主板 / 中小板 / 创业板
        return "sz"
    raise ValueError(f"无法从股票代码推断交易所：{code}。请使用 SH/SZ/BJ 前缀。")


def _market_for_prefix(prefix: str) -> tuple[str, str]:
    if prefix == "sh":
        return "1", "上海证券交易所"
    if prefix == "sz":
        return "0", "深圳证券交易所"
    if prefix == "bj":
        return "0", "北京证券交易所"
    raise ValueError(f"不支持的交易所前缀：{prefix}")
