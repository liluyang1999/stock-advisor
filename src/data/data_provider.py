from __future__ import annotations

import http.client
import json
import math
import time
import urllib.error
import urllib.request
from decimal import Decimal

from domain import money
from domain.models import DailyBar, FundFlow, MarketSnapshot, Quote, StockSymbol
from domain.numeric import finite_float

# 浏览器 UA：含 "Python" 的 UA 会被东方财富 clist 接口拒绝（连接被直接关闭）。
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 单次响应字节上限：read(MAX+1) 后若超限即拒。socket 超时只挡"无数据"，挡不住慢速/巨大响应，
# 少了这道字节墙，一个被中间人替换或行为异常的源可以把任意大的响应整包读进内存。真实行情响应
# 远小于此，此值仅作 DoS / 内存上界。
MAX_RESPONSE_BYTES = 16 * 1024 * 1024  # 16 MiB

# 全市场快照：一次分页调用即可覆盖全 A 股；fs 选取沪深主板/创业板/科创板/北交所。
CLIST_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
CLIST_FIELDS = "f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f20,f21,f22,f23,f24,f25"
# 多个对等主机做回退，提升全市场拉取的成功率。
CLIST_HOSTS = ("push2.eastmoney.com", "push2delay.eastmoney.com")
CLIST_URL = (
    "https://{host}/api/qt/clist/get"
    "?pn={pn}&pz={pz}&po=1&np=1&fltt=2&invt=2&fid=f3"
    f"&fs={CLIST_FS}&fields={CLIST_FIELDS}"
)


QUOTE_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get"
    "?secid={secid}"
    "&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f168,f170"
)
SINA_QUOTE_URL = "https://hq.sinajs.cn/list={symbol}"
HISTORY_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    "?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
    "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    "&klt=101&fqt=1&end=20500101&lmt={limit}"
)
SINA_HISTORY_URL = (
    "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
    "?symbol={symbol}&scale=240&ma=no&datalen={limit}"
)
TENCENT_FQ_HISTORY_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{limit},qfq"
)
TENCENT_HISTORY_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},day,,,{limit}"
)
# 个股资金流（主力净流入日线）。该接口偶发被限流/拒连，调用方需降级处理、不得阻塞主流程。
FUND_FLOW_HOSTS = ("push2.eastmoney.com", "push2his.eastmoney.com")
FUND_FLOW_URL = (
    "https://{host}/api/qt/stock/fflow/kline/get"
    "?lmt={limit}&klt=101&secid={secid}"
    "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57"
)


class MarketDataError(RuntimeError):
    pass


class EastmoneyProvider:
    def __init__(self, timeout: float = 8.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max(1, max_retries)

    def fetch_quote(self, symbol: StockSymbol) -> Quote:
        try:
            payload = self._request(QUOTE_URL.format(secid=symbol.secid))
            return parse_quote_payload(symbol, payload)
        except MarketDataError as primary_error:
            try:
                payload = self._request(
                    SINA_QUOTE_URL.format(symbol=symbol.normalized),
                    headers={"Referer": "https://finance.sina.com.cn/"},
                    encoding="gb18030",
                )
                return parse_sina_quote_payload(symbol, payload)
            except MarketDataError as fallback_error:
                raise MarketDataError(
                    f"实时行情获取失败：{primary_error}；备用源也失败：{fallback_error}"
                ) from fallback_error

    def fetch_history(self, symbol: StockSymbol, limit: int = 120) -> list[DailyBar]:
        limit = _positive_int(limit, 120)
        errors: list[str] = []

        try:
            payload = self._request(HISTORY_URL.format(secid=symbol.secid, limit=limit))
            rows = parse_history_payload(payload)
            if rows:
                return rows
            errors.append("东方财富历史日线为空")
        except (MarketDataError, ValueError) as exc:
            errors.append(f"东方财富历史日线失败：{exc}")

        try:
            payload = self._request(
                SINA_HISTORY_URL.format(symbol=symbol.normalized, limit=limit),
                headers={"Referer": "https://finance.sina.com.cn/"},
                encoding="gb18030",
            )
            rows = parse_sina_history_payload(payload)
            if rows:
                return rows
            errors.append("新浪历史日线为空")
        except (MarketDataError, ValueError) as exc:
            errors.append(f"新浪历史日线失败：{exc}")

        for label, url in (
            (
                "腾讯前复权日线",
                TENCENT_FQ_HISTORY_URL.format(symbol=symbol.normalized, limit=limit),
            ),
            ("腾讯普通日线", TENCENT_HISTORY_URL.format(symbol=symbol.normalized, limit=limit)),
        ):
            try:
                payload = self._request(
                    url,
                    headers={"Referer": "https://gu.qq.com/"},
                )
                rows = parse_tencent_history_payload(symbol, payload)
                if rows:
                    return rows
                errors.append(f"{label}为空")
            except (MarketDataError, ValueError) as exc:
                errors.append(f"{label}失败：{exc}")

        raise MarketDataError("；".join(errors) or "历史日线获取失败")

    def fetch_market_snapshot(
        self, page_size: int = 500, max_pages: int = 20
    ) -> list[MarketSnapshot]:
        """分页拉取全 A 股实时快照，多个对等主机做回退。全部失败才报错。"""
        page_size = _positive_int(page_size, 500)
        max_pages = _positive_int(max_pages, 20)
        errors: list[str] = []
        for host in CLIST_HOSTS:
            try:
                rows = self._fetch_clist_all_pages(host, page_size, max_pages)
            except (MarketDataError, ValueError) as exc:
                errors.append(f"{host} 失败：{exc}")
                continue
            if rows:
                return rows
            errors.append(f"{host} 返回为空")
        raise MarketDataError("全市场行情获取失败：" + "；".join(errors))

    def fetch_fund_flow(self, symbol: StockSymbol, limit: int = 6) -> FundFlow:
        """个股主力资金流（日线）。多主机回退；全部失败才报错，由调用方降级处理。"""
        limit = _positive_int(limit, 6)
        errors: list[str] = []
        for host in FUND_FLOW_HOSTS:
            url = FUND_FLOW_URL.format(host=host, limit=limit, secid=symbol.secid)
            url += f"&_={int(time.time() * 1000)}"
            try:
                payload = self._request(url)
            except (MarketDataError, ValueError) as exc:
                errors.append(f"{host} 失败：{exc}")
                continue
            flow = parse_fund_flow_payload(payload, limit=limit)
            if flow is not None:
                return flow
            errors.append(f"{host} 资金流为空")
        raise MarketDataError("资金流获取失败：" + "；".join(errors))

    def _fetch_clist_all_pages(
        self, host: str, page_size: int, max_pages: int
    ) -> list[MarketSnapshot]:
        collected: list[MarketSnapshot] = []
        seen: set[str] = set()
        total: int | None = None
        for pn in range(1, max(1, int(max_pages)) + 1):
            try:
                # 追加时间戳缓存破坏参数，更接近浏览器请求，规避中间缓存/部分 WAF 拦截。
                url = (
                    CLIST_URL.format(host=host, pn=pn, pz=page_size)
                    + f"&_={int(time.time() * 1000)}"
                )
                payload = self._request(url)
            except MarketDataError, ValueError:
                if pn == 1:
                    raise
                break  # 已取到部分数据，后续页失败则返回已有部分
            if total is None:
                total = _clist_total(payload)
            rows = parse_clist_payload(payload)
            if not rows:
                break
            for row in rows:
                if row.code in seen:
                    continue
                seen.add(row.code)
                collected.append(row)
            if total is not None and len(collected) >= total:
                break
        return collected

    def _request(
        self, url: str, headers: dict[str, str] | None = None, encoding: str | None = None
    ) -> str:
        # 用干净的浏览器 UA：东方财富 clist 等接口会对含 "Python" 的 UA 直接断开连接
        # （Remote end closed connection without response）。不要带 Connection: close。
        merged_headers = {
            "User-Agent": BROWSER_USER_AGENT,
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if headers:
            merged_headers.update(headers)
        request = urllib.request.Request(
            url,
            headers=merged_headers,
        )
        last_error: BaseException | None = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    charset = encoding or response.headers.get_content_charset() or "utf-8"
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise MarketDataError(f"行情响应超过 {MAX_RESPONSE_BYTES} 字节上限")
                    return raw.decode(charset, errors="replace")
            except (
                urllib.error.URLError,
                TimeoutError,
                http.client.RemoteDisconnected,
                ConnectionError,
                OSError,
            ) as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    time.sleep(0.35 * (attempt + 1))
                    continue
        raise MarketDataError(f"行情接口请求失败：{last_error}") from last_error


def parse_quote_payload(symbol: StockSymbol, payload: str) -> Quote:
    data = _json_object(payload).get("data")
    if not isinstance(data, dict):
        raise MarketDataError(f"{symbol.display} 未返回有效实时行情。")

    last = _scaled_price(data.get("f43"), "最新价")
    open_price = _scaled_price(data.get("f46"), "开盘价")
    high = _scaled_price(data.get("f44"), "最高价")
    low = _scaled_price(data.get("f45"), "最低价")
    previous_close = _scaled_price(data.get("f60"), "昨收价")
    high, low = _ohlc_envelope(open_price, last, high, low)
    change_pct = _scaled_percent(data.get("f170"))
    if change_pct is None and previous_close:
        change_pct = float((last - previous_close) / previous_close * 100)

    return Quote(
        symbol=symbol,
        name=str(data.get("f58") or symbol.display),
        last=last,
        open=open_price,
        high=high,
        low=low,
        previous_close=previous_close,
        volume=_nonnegative_int(data.get("f47")),
        amount=_nonnegative_float(data.get("f48")),
        turnover_rate=_scaled_nonnegative_percent(data.get("f168")),
        change_pct=change_pct or 0.0,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def parse_sina_quote_payload(symbol: StockSymbol, payload: str) -> Quote:
    marker = '="'
    start = payload.find(marker)
    end = payload.rfind('"')
    if start < 0 or end <= start + len(marker):
        raise MarketDataError(f"{symbol.display} 备用实时行情结构无效。")
    parts = payload[start + len(marker) : end].split(",")
    if len(parts) < 10 or not parts[0]:
        raise MarketDataError(f"{symbol.display} 备用实时行情为空。")

    name = parts[0]
    open_price = _positive_float(parts[1], "开盘价")
    previous_close = _positive_float(parts[2], "昨收价")
    last = _positive_float(parts[3], "最新价")
    high = _positive_float(parts[4], "最高价")
    low = _positive_float(parts[5], "最低价")
    high, low = _ohlc_envelope(open_price, last, high, low)
    volume = _nonnegative_int(parts[8])
    amount = _nonnegative_float(parts[9])
    change_pct = float((last - previous_close) / previous_close * 100) if previous_close else 0.0
    timestamp = ""
    if len(parts) > 31:
        timestamp = f"{parts[30]} {parts[31]}".strip()

    return Quote(
        symbol=symbol,
        name=name,
        last=last,
        open=open_price,
        high=high,
        low=low,
        previous_close=previous_close,
        volume=volume,
        amount=amount,
        turnover_rate=0.0,
        change_pct=change_pct,
        timestamp=timestamp,
    )


def parse_history_payload(payload: str) -> list[DailyBar]:
    root = _json_object(payload)
    data = root.get("data")
    if not isinstance(data, dict):
        return []

    rows: list[DailyBar] = []
    for line in data.get("klines") or []:
        parts = str(line).split(",")
        if len(parts) < 11:
            continue
        open_price = money.parse_money(parts[1])
        close = money.parse_money(parts[2])
        high = money.parse_money(parts[3])
        low = money.parse_money(parts[4])
        volume = _optional_float(parts[5])
        amount = _optional_float(parts[6])
        pct_change = _optional_float(parts[8])
        turnover_rate = _optional_float(parts[10])
        if (
            open_price is None
            or close is None
            or high is None
            or low is None
            or volume is None
            or amount is None
            or pct_change is None
            or turnover_rate is None
        ):
            continue
        if open_price <= 0 or close <= 0 or high <= 0 or low <= 0:
            continue
        if volume < 0 or amount < 0 or turnover_rate < 0:
            continue
        high, low = _ohlc_envelope(open_price, close, high, low)
        rows.append(
            DailyBar(
                date=parts[0],
                open=open_price,
                close=close,
                high=high,
                low=low,
                volume=int(volume),
                amount=amount,
                pct_change=pct_change,
                turnover_rate=turnover_rate,
            )
        )
    return rows


def parse_sina_history_payload(payload: str) -> list[DailyBar]:
    items = _json_array(payload)
    rows: list[DailyBar] = []
    previous_close: Decimal | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        bar = _daily_bar_from_ohlcv(
            date=item.get("day"),
            open_value=item.get("open"),
            close_value=item.get("close"),
            high_value=item.get("high"),
            low_value=item.get("low"),
            volume_value=item.get("volume"),
            previous_close=previous_close,
        )
        if bar is None:
            continue
        rows.append(bar)
        previous_close = bar.close
    return rows


def parse_tencent_history_payload(symbol: StockSymbol, payload: str) -> list[DailyBar]:
    root = _json_object(payload)
    data = root.get("data")
    if not isinstance(data, dict):
        return []

    bucket = data.get(symbol.normalized) or data.get(symbol.normalized.upper())
    if not isinstance(bucket, dict):
        return []

    raw_rows = bucket.get("qfqday") or bucket.get("day") or []
    if not isinstance(raw_rows, list):
        return []

    rows: list[DailyBar] = []
    previous_close: Decimal | None = None
    for item in raw_rows:
        if not isinstance(item, list | tuple) or len(item) < 6:
            continue
        bar = _daily_bar_from_ohlcv(
            date=item[0],
            open_value=item[1],
            close_value=item[2],
            high_value=item[3],
            low_value=item[4],
            volume_value=item[5],
            previous_close=previous_close,
            volume_multiplier=100,
        )
        if bar is None:
            continue
        rows.append(bar)
        previous_close = bar.close
    return rows


def parse_clist_payload(payload: str) -> list[MarketSnapshot]:
    """解析东方财富全市场列表（clist）。缺失字段记 None，无效价格行跳过。"""
    data = _json_object(payload).get("data")
    if not isinstance(data, dict):
        return []
    diff = data.get("diff")
    if not isinstance(diff, list):
        return []

    rows: list[MarketSnapshot] = []
    for item in diff:
        if not isinstance(item, dict):
            continue
        price = money.parse_money(item.get("f2"))
        code = str(item.get("f12") or "").strip()
        if price is None or price <= 0 or not code:
            continue
        change_pct = _optional_float(item.get("f3"))
        change = money.parse_money(item.get("f4"))
        volume = _optional_float(item.get("f5"))
        amount = _optional_float(item.get("f6"))
        amplitude = _optional_float(item.get("f7"))
        turnover_rate = _optional_float(item.get("f8"))
        if (
            change_pct is None
            or change is None
            or volume is None
            or amount is None
            or amplitude is None
            or turnover_rate is None
        ):
            continue
        market_id = _market_id(item.get("f13"))
        if market_id is None:
            continue
        rows.append(
            MarketSnapshot(
                code=code,
                market_id=market_id,
                name=str(item.get("f14") or code),
                price=price,
                change_pct=change_pct,
                change=change,
                volume=int(max(0.0, volume)),
                amount=max(0.0, amount),
                amplitude=max(0.0, amplitude),
                turnover_rate=max(0.0, turnover_rate),
                pe_ttm=_optional_float(item.get("f9")),
                volume_ratio=_optional_nonnegative_float(item.get("f10")),
                total_cap=_optional_nonnegative_float(item.get("f20")),
                float_cap=_optional_nonnegative_float(item.get("f21")),
                speed=_optional_float(item.get("f22")),
                pb=_optional_float(item.get("f23")),
                change_60d=_optional_float(item.get("f24")),
                change_ytd=_optional_float(item.get("f25")),
            )
        )
    return rows


def _market_id(value: object) -> str | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    market = int(number)
    return str(market) if market in (0, 1) else None


def parse_fund_flow_payload(payload: str, limit: int = 5) -> FundFlow | None:
    """解析资金流日线（klines 每行：日期, 主力净额, 小单, 中单, 大单, 超大单）。无有效行返回 None。"""
    data = _json_object(payload).get("data")
    if not isinstance(data, dict):
        return None
    rows: list[tuple[str, float]] = []
    for line in data.get("klines") or []:
        parts = str(line).split(",")
        if len(parts) < 2 or not parts[0]:
            continue
        value = _optional_float(parts[1])
        if value is None:
            continue
        rows.append((parts[0], value))
    if not rows:
        return None
    recent = rows[-_positive_int(limit, 5) :]
    return FundFlow(
        today_main=rows[-1][1], main_5d=sum(value for _, value in rows[-5:]), recent=recent
    )


def _clist_total(payload: str) -> int | None:
    try:
        data = _json_object(payload).get("data")
    except MarketDataError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        total = float(data.get("total"))  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    if not math.isfinite(total) or total < 0:
        return None
    return int(total)


def _optional_float(value: object) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _optional_nonnegative_float(value: object) -> float | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    return number


def _ohlc_envelope(
    open_price: Decimal, close_or_last: Decimal, high: Decimal, low: Decimal
) -> tuple[Decimal, Decimal]:
    return max(high, open_price, close_or_last), min(low, open_price, close_or_last)


def _positive_int(value: object, default: int) -> int:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return max(1, int(default))
    if not math.isfinite(number):
        return max(1, int(default))
    return max(1, int(number))


def _json_object(payload: str) -> dict:
    text = payload.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        root = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MarketDataError(f"行情接口返回不是有效 JSON：{exc}") from exc
    if not isinstance(root, dict):
        raise MarketDataError("行情接口返回结构无效。")
    return root


def _json_array(payload: str) -> list:
    text = payload.strip()
    if not text.startswith("["):
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        root = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MarketDataError(f"行情接口返回不是有效 JSON 数组：{exc}") from exc
    if not isinstance(root, list):
        raise MarketDataError("行情接口返回结构无效。")
    return root


def _daily_bar_from_ohlcv(
    *,
    date: object,
    open_value: object,
    close_value: object,
    high_value: object,
    low_value: object,
    volume_value: object,
    previous_close: Decimal | None,
    volume_multiplier: int = 1,
) -> DailyBar | None:
    date_text = str(date or "").strip()
    open_price = money.parse_money(open_value)
    close = money.parse_money(close_value)
    high = money.parse_money(high_value)
    low = money.parse_money(low_value)
    if not date_text or open_price is None or open_price <= 0 or close is None or close <= 0:
        return None
    if high is None or high <= 0:
        high = max(open_price, close)
    if low is None or low <= 0:
        low = min(open_price, close)
    high = max(high, open_price, close)
    low = min(low, open_price, close)

    raw_volume = _optional_float(volume_value)
    if raw_volume is None or raw_volume < 0:
        return None
    volume = int(raw_volume * volume_multiplier)
    pct_change = 0.0
    if previous_close and previous_close > 0:
        pct_change = float((close - previous_close) / previous_close * 100)
    return DailyBar(
        date=date_text,
        open=open_price,
        close=close,
        high=high,
        low=low,
        volume=volume,
        amount=float(volume * close),
        pct_change=round(pct_change, 4),
        turnover_rate=0.0,
    )


def _scaled_price(value: object, label: str) -> Decimal:
    price = money.scaled_price(value, 100)
    if price is None or price <= 0:
        raise MarketDataError(f"{label} 缺失或无效。")
    return price


def _positive_float(value: object, label: str) -> Decimal:
    price = money.positive_money(value)
    if price is None:
        raise MarketDataError(f"{label} 缺失或无效。")
    return price


def _scaled_percent(value: object) -> float | None:
    # 无效涨跌幅必须保留缺失语义，让报价入口按最新价/昨收价重算；零值是有效数据。
    number = finite_float(value)
    return None if number is None else round(number / 100, 4)


def _scaled_nonnegative_percent(value: object) -> float:
    number = _scaled_percent(value)
    if number is None or number < 0:
        return 0.0
    return number


def _safe_float(value: object) -> float:
    if value in (None, "", "-"):
        return 0.0
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return 0.0
    return number if math.isfinite(number) else 0.0


def _nonnegative_float(value: object) -> float:
    return max(0.0, _safe_float(value))


def _nonnegative_int(value: object) -> int:
    return int(_nonnegative_float(value))
