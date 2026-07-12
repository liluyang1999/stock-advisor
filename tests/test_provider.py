import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.data.data_provider import (
    EastmoneyProvider,
    MarketDataError,
    parse_clist_payload,
    parse_history_payload,
    parse_fund_flow_payload,
    parse_quote_payload,
    parse_sina_quote_payload,
    parse_sina_history_payload,
    parse_tencent_history_payload,
)
from stock_advisor.domain.symbols import normalize_symbol


def clist_item(code="600001", market=1, name="stock", price=10.0, change_pct=1.0, **overrides):
    item = {
        "f12": code,
        "f13": market,
        "f14": name,
        "f2": price,
        "f3": change_pct,
        "f4": 0.1,
        "f5": 100000,
        "f6": 100000000,
        "f7": 2.0,
        "f8": 1.0,
    }
    item.update(overrides)
    return item


class ProviderParsingTests(unittest.TestCase):
    def test_parse_quote_payload_converts_eastmoney_scaled_fields(self):
        payload = json.dumps(
            {
                "data": {
                    "f57": "600519",
                    "f58": "贵州茅台",
                    "f43": 171234,
                    "f46": 170000,
                    "f44": 172000,
                    "f45": 169500,
                    "f60": 168000,
                    "f47": 250000,
                    "f48": 4220000000,
                    "f168": 110,
                    "f170": 192,
                }
            },
            ensure_ascii=False,
        )

        quote = parse_quote_payload(normalize_symbol("600519"), payload)

        self.assertEqual(quote.name, "贵州茅台")
        self.assertAlmostEqual(quote.last, 1712.34)
        self.assertAlmostEqual(quote.open, 1700.0)
        self.assertAlmostEqual(quote.high, 1720.0)
        self.assertAlmostEqual(quote.low, 1695.0)
        self.assertAlmostEqual(quote.previous_close, 1680.0)
        self.assertAlmostEqual(quote.change_pct, 1.92)
        self.assertAlmostEqual(quote.turnover_rate, 1.1)

    def test_parse_quote_payload_scales_eastmoney_percent_boundary_values(self):
        payload = json.dumps(
            {
                "data": {
                    "f58": "百分比边界",
                    "f43": 10100,
                    "f46": 10000,
                    "f44": 10200,
                    "f45": 9900,
                    "f60": 10000,
                    "f168": 100,
                    "f170": 100,
                }
            },
            ensure_ascii=False,
        )

        quote = parse_quote_payload(normalize_symbol("600519"), payload)

        self.assertAlmostEqual(quote.turnover_rate, 1.0)
        self.assertAlmostEqual(quote.change_pct, 1.0)

    def test_parse_quote_payload_rejects_non_finite_required_price(self):
        payload = json.dumps(
            {
                "data": {
                    "f58": "异常股",
                    "f43": "NaN",
                    "f46": 1000,
                    "f44": 1010,
                    "f45": 990,
                    "f60": 1000,
                }
            },
            ensure_ascii=False,
        )

        with self.assertRaises(MarketDataError):
            parse_quote_payload(normalize_symbol("600519"), payload)

    def test_parse_quote_payload_clamps_negative_physical_fields(self):
        payload = json.dumps(
            {
                "data": {
                    "f58": "异常量",
                    "f43": 1000,
                    "f46": 1000,
                    "f44": 1010,
                    "f45": 990,
                    "f60": 1000,
                    "f47": -500,
                    "f48": -1000000,
                    "f168": -120,
                    "f170": -50,
                }
            },
            ensure_ascii=False,
        )

        quote = parse_quote_payload(normalize_symbol("600519"), payload)

        self.assertEqual(quote.volume, 0)
        self.assertEqual(quote.amount, 0.0)
        self.assertEqual(quote.turnover_rate, 0.0)
        self.assertLess(quote.change_pct, 0)

    def test_parse_quote_payload_normalizes_inconsistent_ohlc_envelope(self):
        payload = json.dumps(
            {
                "data": {
                    "f58": "bad envelope",
                    "f43": 1050,
                    "f46": 1000,
                    "f44": 990,
                    "f45": 1020,
                    "f60": 1000,
                }
            }
        )

        quote = parse_quote_payload(normalize_symbol("600519"), payload)

        self.assertAlmostEqual(quote.high, 10.5)
        self.assertAlmostEqual(quote.low, 10.0)

    def test_parse_sina_quote_payload_as_realtime_fallback(self):
        payload = (
            'var hq_str_sh600519="贵州茅台,1235.000,1240.000,1215.000,'
            '1238.870,1211.220,1215.000,1215.280,5747173,7016713941.000,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-06-19,15:00:00,00,";'
        )

        quote = parse_sina_quote_payload(normalize_symbol("600519"), payload)

        self.assertEqual(quote.name, "贵州茅台")
        self.assertAlmostEqual(quote.open, 1235.0)
        self.assertAlmostEqual(quote.previous_close, 1240.0)
        self.assertAlmostEqual(quote.last, 1215.0)
        self.assertAlmostEqual(quote.high, 1238.87)
        self.assertAlmostEqual(quote.low, 1211.22)
        self.assertLess(quote.change_pct, 0)

    def test_parse_sina_quote_payload_clamps_negative_physical_fields(self):
        payload = (
            'var hq_str_sh600519="贵州茅台,10.000,10.000,9.900,'
            '10.100,9.800,9.900,9.910,-5747173,-7016713941.000,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-06-19,15:00:00,00,";'
        )

        quote = parse_sina_quote_payload(normalize_symbol("600519"), payload)

        self.assertEqual(quote.volume, 0)
        self.assertEqual(quote.amount, 0.0)

    def test_parse_sina_quote_payload_normalizes_inconsistent_ohlc_envelope(self):
        payload = (
            'var hq_str_sh600519="bad envelope,10.000,10.000,10.500,'
            '9.900,10.200,10.500,10.510,1000,10500.000,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-06-19,15:00:00,00,";'
        )

        quote = parse_sina_quote_payload(normalize_symbol("600519"), payload)

        self.assertAlmostEqual(quote.high, 10.5)
        self.assertAlmostEqual(quote.low, 10.0)

    def test_parse_history_payload_keeps_valid_rows(self):
        payload = json.dumps(
            {
                "data": {
                    "klines": [
                        "2026-06-18,10.00,10.50,10.70,9.90,100000,105000000,8.0,5.0,0.5,1.2",
                        "2026-06-19,10.50,10.20,10.60,10.10,120000,124000000,4.8,-2.86,-0.3,1.4",
                    ]
                }
            }
        )

        rows = parse_history_payload(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, "2026-06-18")
        self.assertAlmostEqual(rows[1].close, 10.2)
        self.assertEqual(rows[1].volume, 120000)

    def test_parse_history_payload_drops_non_finite_rows(self):
        payload = json.dumps(
            {
                "data": {
                    "klines": [
                        "2026-06-18,NaN,10.50,10.70,9.90,100000,105000000,8.0,5.0,0.5,1.2",
                        "2026-06-19,10.50,10.20,10.60,10.10,Infinity,124000000,4.8,-2.86,-0.3,1.4",
                        "2026-06-20,10.20,10.40,10.50,10.00,90000,93000000,4.2,1.96,0.2,1.1",
                    ]
                }
            }
        )

        rows = parse_history_payload(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].date, "2026-06-20")

    def test_parse_history_payload_normalizes_inconsistent_ohlc_envelope(self):
        payload = json.dumps(
            {
                "data": {
                    "klines": [
                        "2026-06-18,10.00,10.50,9.80,10.20,100000,105000000,8.0,5.0,0.5,1.2",
                    ]
                }
            }
        )

        rows = parse_history_payload(payload)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].high, 10.5)
        self.assertAlmostEqual(rows[0].low, 10.0)

    def test_parse_sina_history_payload_as_daily_fallback(self):
        payload = json.dumps(
            [
                {
                    "day": "2026-06-18",
                    "open": "10.00",
                    "high": "10.70",
                    "low": "9.90",
                    "close": "10.50",
                    "volume": "100000",
                },
                {
                    "day": "2026-06-19",
                    "open": "10.50",
                    "high": "10.60",
                    "low": "10.10",
                    "close": "10.20",
                    "volume": "120000",
                },
            ]
        )

        rows = parse_sina_history_payload(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, "2026-06-18")
        self.assertAlmostEqual(rows[1].pct_change, -2.8571, places=3)
        self.assertEqual(rows[1].volume, 120000)

    def test_parse_sina_history_payload_drops_negative_volume_rows(self):
        payload = json.dumps(
            [
                {
                    "day": "2026-06-18",
                    "open": "10.00",
                    "high": "10.70",
                    "low": "9.90",
                    "close": "10.50",
                    "volume": "-100000",
                },
                {
                    "day": "2026-06-19",
                    "open": "10.50",
                    "high": "10.60",
                    "low": "10.10",
                    "close": "10.20",
                    "volume": "120000",
                },
            ]
        )

        rows = parse_sina_history_payload(payload)

        self.assertEqual([row.date for row in rows], ["2026-06-19"])
        self.assertGreaterEqual(rows[0].volume, 0)

    def test_parse_sina_history_payload_drops_non_finite_volume_rows(self):
        payload = json.dumps(
            [
                {
                    "day": "2026-06-18",
                    "open": "10.00",
                    "high": "10.70",
                    "low": "9.90",
                    "close": "10.50",
                    "volume": "NaN",
                },
                {
                    "day": "2026-06-19",
                    "open": "10.50",
                    "high": "10.60",
                    "low": "10.10",
                    "close": "10.20",
                    "volume": "120000",
                },
            ]
        )

        rows = parse_sina_history_payload(payload)

        self.assertEqual([row.date for row in rows], ["2026-06-19"])

    def test_parse_tencent_history_payload_as_daily_fallback(self):
        payload = json.dumps(
            {
                "data": {
                    "sh600519": {
                        "qfqday": [
                            ["2026-06-18", "10.00", "10.50", "10.70", "9.90", "1000"],
                            ["2026-06-19", "10.50", "10.20", "10.60", "10.10", "1200"],
                        ]
                    }
                }
            }
        )

        rows = parse_tencent_history_payload(normalize_symbol("600519"), payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, "2026-06-18")
        self.assertAlmostEqual(rows[1].close, 10.2)
        self.assertEqual(rows[1].volume, 120000)

    def test_parse_tencent_history_payload_drops_negative_volume_rows(self):
        payload = json.dumps(
            {
                "data": {
                    "sh600519": {
                        "qfqday": [
                            ["2026-06-18", "10.00", "10.50", "10.70", "9.90", "-1000"],
                            ["2026-06-19", "10.50", "10.20", "10.60", "10.10", "1200"],
                        ]
                    }
                }
            }
        )

        rows = parse_tencent_history_payload(normalize_symbol("600519"), payload)

        self.assertEqual([row.date for row in rows], ["2026-06-19"])
        self.assertGreaterEqual(rows[0].volume, 0)

    def test_parse_tencent_history_payload_drops_non_finite_volume_rows(self):
        payload = json.dumps(
            {
                "data": {
                    "sh600519": {
                        "qfqday": [
                            ["2026-06-18", "10.00", "10.50", "10.70", "9.90", "Infinity"],
                            ["2026-06-19", "10.50", "10.20", "10.60", "10.10", "1200"],
                        ]
                    }
                }
            }
        )

        rows = parse_tencent_history_payload(normalize_symbol("600519"), payload)

        self.assertEqual([row.date for row in rows], ["2026-06-19"])

    def test_fetch_history_falls_back_to_sina_when_primary_history_fails(self):
        payload = json.dumps(
            [
                {
                    "day": "2026-06-18",
                    "open": "10.00",
                    "high": "10.70",
                    "low": "9.90",
                    "close": "10.50",
                    "volume": "100000",
                }
            ]
        )
        provider = EastmoneyProvider(timeout=0.1, max_retries=1)

        def fake_request(url, **_kwargs):
            if "push2his" in url:
                raise MarketDataError("primary closed")
            return payload

        with patch.object(provider, "_request", fake_request):
            rows = provider.fetch_history(normalize_symbol("600519"), limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].date, "2026-06-18")

    def test_fetch_history_falls_back_to_tencent_when_sina_history_fails(self):
        payload = json.dumps(
            {
                "data": {
                    "sh600519": {
                        "qfqday": [
                            ["2026-06-18", "10.00", "10.50", "10.70", "9.90", "1000"],
                        ]
                    }
                }
            }
        )
        provider = EastmoneyProvider(timeout=0.1, max_retries=1)

        def fake_request(url, **_kwargs):
            if "push2his" in url or "sina" in url:
                raise MarketDataError("source closed")
            return payload

        with patch.object(provider, "_request", fake_request):
            rows = provider.fetch_history(normalize_symbol("600519"), limit=1)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].close, 10.5)

    def test_parse_clist_payload_reads_snapshot_fields_and_handles_missing(self):
        payload = json.dumps(
            {
                "rc": 0,
                "data": {
                    "total": 2,
                    "diff": [
                        {
                            "f12": "600519", "f13": 1, "f14": "贵州茅台",
                            "f2": 1712.34, "f3": 1.92, "f4": 32.3, "f5": 250000,
                            "f6": 4220000000, "f7": 1.5, "f8": 0.21, "f9": 28.5,
                            "f10": 1.1, "f20": 2150000000000, "f21": 2150000000000,
                            "f22": 0.3, "f23": 8.2, "f24": 5.6, "f25": 12.3,
                        },
                        {
                            "f12": "300999", "f13": 0, "f14": "金龙鱼",
                            "f2": 30.5, "f3": -2.1, "f4": -0.65, "f5": 120000,
                            "f6": 360000000, "f7": 3.2, "f8": 1.8, "f9": "-",
                            "f10": "-", "f20": 165000000000, "f21": 80000000000,
                            "f22": "-", "f23": 2.1, "f24": "-", "f25": "-",
                        },
                    ],
                },
            },
            ensure_ascii=False,
        )

        rows = parse_clist_payload(payload)

        self.assertEqual(len(rows), 2)
        moutai = rows[0]
        self.assertEqual(moutai.code, "600519")
        self.assertEqual(moutai.market_id, "1")
        self.assertEqual(moutai.name, "贵州茅台")
        self.assertAlmostEqual(moutai.price, 1712.34)
        self.assertAlmostEqual(moutai.change_pct, 1.92)
        self.assertAlmostEqual(moutai.pe_ttm, 28.5)
        self.assertAlmostEqual(moutai.volume_ratio, 1.1)
        # 缺失字段（"-"）应记为 None，不应抛错
        missing = rows[1]
        self.assertIsNone(missing.pe_ttm)
        self.assertIsNone(missing.volume_ratio)
        self.assertIsNone(missing.speed)
        self.assertIsNone(missing.change_60d)
        self.assertIsNone(missing.change_ytd)
        self.assertEqual(missing.market_id, "0")

    def test_parse_clist_payload_keeps_negative_pe_for_loss_making_stocks(self):
        payload = json.dumps(
            {"data": {"diff": [clist_item(code="688001", name="亏损股", price=12.0, change_pct=0.5, f9=-197.0)]}}
        )

        rows = parse_clist_payload(payload)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].pe_ttm, -197.0)

    def test_parse_clist_payload_skips_rows_without_valid_price(self):
        payload = json.dumps(
            {
                "data": {
                    "diff": [
                        {"f12": "600000", "f13": 1, "f14": "停牌股", "f2": "-", "f3": 0.0},
                        clist_item(code="600001", name="正常股", price=10.0, change_pct=1.0),
                    ]
                }
            }
        )

        rows = parse_clist_payload(payload)

        self.assertEqual([row.code for row in rows], ["600001"])

    def test_parse_clist_payload_drops_non_finite_numbers(self):
        payload = json.dumps(
            {
                "data": {
                    "diff": [
                        clist_item(code="600000", name="异常价", price="NaN", change_pct=0.0),
                        clist_item(code="600001", name="异常涨跌", change_pct="Infinity"),
                        clist_item(code="600002", name="正常股", f9="NaN", f10=1.2),
                    ]
                }
            },
            allow_nan=False,
        )

        rows = parse_clist_payload(payload)

        self.assertEqual([row.code for row in rows], ["600002"])
        self.assertEqual(rows[0].change_pct, 1.0)
        self.assertIsNone(rows[0].pe_ttm)
        self.assertAlmostEqual(rows[0].volume_ratio, 1.2)

    def test_parse_clist_payload_skips_rows_missing_required_market_fields(self):
        payload = json.dumps(
            {
                "data": {
                    "diff": [
                        clist_item(code="good"),
                        clist_item(code="no_change_pct", f3="-"),
                        clist_item(code="no_change", f4="-"),
                        clist_item(code="no_volume", f5="NaN"),
                        clist_item(code="no_amount", f6="-"),
                        clist_item(code="no_amplitude", f7="Infinity"),
                        clist_item(code="no_turnover", f8=""),
                    ]
                }
            },
            allow_nan=False,
        )

        rows = parse_clist_payload(payload)

        self.assertEqual([row.code for row in rows], ["good"])

    def test_parse_clist_payload_normalizes_and_requires_market_id(self):
        payload = json.dumps(
            {
                "data": {
                    "diff": [
                        clist_item(code="600001", market=1.0),
                        clist_item(code="300001", market="0.0"),
                        clist_item(code="600002", market="2"),
                        clist_item(code="600003", market="-"),
                        clist_item(code="600004", market=None),
                    ]
                }
            }
        )

        rows = parse_clist_payload(payload)

        self.assertEqual([(row.code, row.market_id) for row in rows], [("600001", "1"), ("300001", "0")])

    def test_parse_clist_payload_sanitizes_negative_physical_fields(self):
        payload = json.dumps(
            {
                "data": {
                    "diff": [
                        {
                            "f12": "600001", "f13": 1, "f14": "异常物理量", "f2": 10.0,
                            "f3": -2.0, "f4": -0.2, "f5": -100, "f6": -200000,
                            "f7": -3.5, "f8": -1.2, "f10": -2.0,
                        },
                    ]
                }
            },
            ensure_ascii=False,
        )

        rows = parse_clist_payload(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.volume, 0)
        self.assertEqual(row.amount, 0.0)
        self.assertEqual(row.amplitude, 0.0)
        self.assertEqual(row.turnover_rate, 0.0)
        self.assertIsNone(row.volume_ratio)
        self.assertLess(row.change_pct, 0)

    def test_parse_clist_payload_sanitizes_negative_market_caps(self):
        payload = json.dumps(
            {
                "data": {
                    "diff": [
                        clist_item(code="600001", f20=-100000000, f21=-50000000),
                    ]
                }
            }
        )

        rows = parse_clist_payload(payload)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].total_cap)
        self.assertIsNone(rows[0].float_cap)

    def test_parse_fund_flow_payload_drops_non_finite_rows(self):
        payload = json.dumps(
            {
                "data": {
                    "klines": [
                        "2026-06-18,NaN,0,0,0,0",
                        "2026-06-19,100.5,0,0,0,0",
                        "2026-06-20,Infinity,0,0,0,0",
                    ]
                }
            }
        )

        flow = parse_fund_flow_payload(payload, limit=5)

        self.assertIsNotNone(flow)
        assert flow is not None
        self.assertAlmostEqual(flow.today_main, 100.5)
        self.assertAlmostEqual(flow.main_5d, 100.5)
        self.assertEqual(flow.recent, [("2026-06-19", 100.5)])

    def test_parse_clist_payload_returns_empty_when_no_data(self):
        self.assertEqual(parse_clist_payload(json.dumps({"data": None})), [])
        self.assertEqual(parse_clist_payload(json.dumps({"data": {"diff": None}})), [])

    def test_fetch_market_snapshot_pages_until_total_reached(self):
        def page(codes):
            return json.dumps(
                {
                    "data": {
                        "total": 3,
                        "diff": [
                            clist_item(code=code, name=f"股票{code}", price=10.0 + i, change_pct=1.0)
                            for i, code in enumerate(codes)
                        ],
                    }
                }
            )

        pages = {1: page(["600001", "600002"]), 2: page(["600003"])}
        seen = {"pages": []}

        def fake_request(url, **_kwargs):
            import re as _re
            pn = int(_re.search(r"pn=(\d+)", url).group(1))
            seen["pages"].append(pn)
            return pages.get(pn, json.dumps({"data": {"total": 3, "diff": []}}))

        provider = EastmoneyProvider(timeout=0.1, max_retries=1)
        with patch.object(provider, "_request", fake_request):
            rows = provider.fetch_market_snapshot(page_size=2)

        self.assertEqual([row.code for row in rows], ["600001", "600002", "600003"])
        self.assertEqual(seen["pages"][:2], [1, 2])

    def test_fetch_market_snapshot_treats_non_finite_total_as_unknown(self):
        pages = {
            1: json.dumps({"data": {"total": float("nan"), "diff": [clist_item(code="600001")]}}),
            2: json.dumps({"data": {"total": float("nan"), "diff": []}}),
        }

        def fake_request(url, **_kwargs):
            import re as _re

            pn = int(_re.search(r"pn=(\d+)", url).group(1))
            return pages[pn]

        provider = EastmoneyProvider(timeout=0.1, max_retries=1)
        with patch.object(provider, "_request", fake_request):
            rows = provider.fetch_market_snapshot(page_size=1)

        self.assertEqual([row.code for row in rows], ["600001"])

    def test_fetch_market_snapshot_raises_when_first_page_fails(self):
        provider = EastmoneyProvider(timeout=0.1, max_retries=1)

        def fake_request(url, **_kwargs):
            raise MarketDataError("clist closed")

        with patch.object(provider, "_request", fake_request):
            with self.assertRaises(MarketDataError):
                provider.fetch_market_snapshot()

    def test_request_retries_transient_connection_failure(self):
        class FakeHeaders:
            def get_content_charset(self):
                return "utf-8"

        class FakeResponse:
            headers = FakeHeaders()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"data":{}}'

        calls = {"count": 0}

        def fake_urlopen(_request, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionResetError("reset")
            return FakeResponse()

        provider = EastmoneyProvider(timeout=0.1, max_retries=2)
        with patch("urllib.request.urlopen", fake_urlopen):
            payload = provider._request("https://example.test")

        self.assertEqual(payload, '{"data":{}}')
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
