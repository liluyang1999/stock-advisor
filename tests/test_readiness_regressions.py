"""Regression contracts for calendar order, cancellation, data quality and corrupt configuration."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from threading import Event
from unittest.mock import patch

from PySide6 import QtWidgets

from data.bounded_adapter import BoundedMarketDataProvider
from data.bounded_transport import BoundedUrllibProvider
from data.data_provider import (
    parse_history_payload,
    parse_sina_history_payload,
    parse_tencent_history_payload,
)
from domain.backtest import backtest_signals
from domain.engine import build_analysis_result, measure
from domain.history import chronological_history
from domain.models import AlertRule, FilterCriteria
from domain.policy import decide
from domain.symbols import normalize_symbol
from ports import Completeness, Deadline, ManualCancel, TransportOutcome
from qt_app.controllers.alert_controller import AlertController
from qt_app.controllers.analysis_controller import AnalysisController
from services.batch import run_batch_analysis
from services.workflow import analyze_symbol, screen_and_recommend
from tests.test_bounded_transport import _clist_payload, _quote_payload
from tests.test_engine import fake_quote
from tests.test_screener import snap
from ui.view_format import format_results_as_csv, format_results_for_clipboard
from ui.view_text import build_detail_text

SYMBOL = normalize_symbol("600000")


def history_payload(count=45, *, reverse=False, duplicate=False):
    rows = []
    for i in range(count):
        day = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        price = Decimal("10") + Decimal(i) / 10
        rows.append(f"{day},{price},{price},{price},{price},1000,10000,0,0,0,1")
    if reverse:
        rows.reverse()
    if duplicate:
        rows.append(rows[-1])
    return json.dumps({"data": {"klines": rows}})


class TransportTerminalTests(unittest.TestCase):
    def test_market_pagination_handles_server_page_cap_and_stable_order(self):
        from urllib.parse import parse_qs, urlsplit

        queries = []

        def opener(request, timeout, encoding):
            query = parse_qs(urlsplit(request.full_url).query)
            queries.append(query)
            start = (int(query["pn"][0]) - 1) * 100
            return _clist_payload(
                [str(600000 + i) for i in range(start, min(start + 100, 2101))], total=2101
            )

        outcome = BoundedUrllibProvider(opener=opener).fetch_market_snapshot()
        self.assertTrue(outcome.succeeded)
        self.assertTrue(outcome.completeness.is_complete)
        self.assertEqual(len(outcome.data), 2101)
        self.assertTrue(all(q["fid"] == ["f12"] for q in queries))

    def test_market_cancel_wins_over_late_failure_or_parse_error(self):
        for response in ("{", None):
            token = ManualCancel()

            def opener(request, timeout, encoding, response=response, token=token):
                token.cancel()
                if response is None:
                    raise TimeoutError("cancelled request failed")
                return response

            outcome = BoundedUrllibProvider(opener=opener).fetch_market_snapshot(cancel_token=token)
            self.assertTrue(outcome.cancelled)
            self.assertFalse(outcome.succeeded)

    def test_cancel_during_final_history_does_not_publish_success(self):
        token = ManualCancel()

        def opener(request, timeout, encoding):
            if "kline" in request.full_url:
                token.cancel()
                return history_payload()
            return _quote_payload()

        provider = BoundedMarketDataProvider(BoundedUrllibProvider(opener=opener))
        provider.set_cancel_token(token)
        report = run_batch_analysis("600000", provider, cancel_token=token)
        self.assertTrue(
            report.cancelled,
            "The last in-flight response completed after cancel but the batch reports normal completion.",
        )
        self.assertEqual(report.success_count, 0)

    def test_success_arriving_after_deadline_is_not_accepted(self):
        now = [0.0]

        def opener(request, timeout, encoding):
            now[0] = 21.0
            return _quote_payload()

        provider = BoundedUrllibProvider(opener=opener, clock=lambda: now[0])
        outcome = provider.fetch_quote(SYMBOL, deadline=Deadline.start(20, clock=lambda: now[0]))
        self.assertFalse(outcome.succeeded)

    def test_cancelled_partial_screen_keeps_completeness(self):
        token = ManualCancel()
        partial = Completeness(expected=100, received=2, missing_pages=(2,))

        class Provider:
            def fetch_market_snapshot_outcome(self):
                return TransportOutcome.ok(
                    [snap(code="600000"), snap(code="600001")], completeness=partial
                )

        def progress(*args):
            token.cancel()

        report = screen_and_recommend(
            Provider(),
            FilterCriteria(),
            "balanced",
            deep=False,
            cancel_event=token,
            progress_cb=progress,
        )
        self.assertTrue(report.cancelled)
        self.assertEqual(report.completeness, partial)


class ChronologyTests(unittest.TestCase):
    def test_fallback_history_percentages_follow_calendar_order(self):
        sina = [
            {
                "day": f"2026-01-0{i}",
                "open": str(price),
                "close": str(price),
                "high": str(price),
                "low": str(price),
                "volume": "100",
            }
            for i, price in ((2, 11), (1, 10))
        ]
        tencent = {
            "data": {
                SYMBOL.normalized: {
                    "qfqday": [
                        [r["day"], r["open"], r["close"], r["high"], r["low"], r["volume"]]
                        for r in sina
                    ]
                }
            }
        }
        for bars in (
            parse_sina_history_payload(json.dumps(sina)),
            parse_tencent_history_payload(SYMBOL, json.dumps(tencent)),
        ):
            self.assertEqual([b.pct_change for b in bars], [0.0, 10.0])

    def test_ambiguous_or_invalid_dates_are_rejected(self):
        bars = parse_history_payload(history_payload())
        with self.assertRaises(ValueError):
            chronological_history([bars[0], replace(bars[0], close=Decimal("99"))])
        with self.assertRaises(ValueError):
            chronological_history([replace(bars[0], date="2026-02-30")])

    def test_backtest_rejects_or_normalizes_reverse_dated_history(self):
        history = parse_history_payload(history_payload(reverse=True))
        leaked = []

        def observe(quote, as_of):
            signal_day = as_of[-1].date
            future = [bar.date for bar in as_of if bar.date > signal_day]
            if future:
                leaked.append({"signal_date": signal_day, "latest_input_date": max(future)})
            return measure(quote, as_of)

        with patch("domain.backtest.measure", side_effect=observe):
            report = backtest_signals(history)
        self.assertFalse(report.ok and leaked, "Calendar-future bars are consumed as past data.")

    def test_duplicate_dates_do_not_inflate_samples(self):
        normal = parse_history_payload(history_payload())
        duplicate = parse_history_payload(history_payload(duplicate=True))
        normal_report = backtest_signals(normal)
        duplicate_report = backtest_signals(duplicate)
        self.assertTrue(
            not duplicate_report.ok or duplicate_report.sample_size == normal_report.sample_size
        )


class QualityTests(unittest.TestCase):
    def test_production_history_normalization_is_visible_in_exports(self):
        def opener(request, timeout, encoding):
            return (
                history_payload(reverse=True, duplicate=True)
                if "kline" in request.full_url
                else _quote_payload()
            )

        outcome = analyze_symbol(
            SYMBOL, BoundedMarketDataProvider(BoundedUrllibProvider(opener=opener))
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(len(outcome.history), 45)
        for text in (
            outcome.result.data_note,
            format_results_as_csv([outcome.result]),
            format_results_for_clipboard([outcome.result]),
        ):
            self.assertIn("46", text)
            self.assertIn("45", text)
            self.assertIn("排序", text)
            self.assertIn("重复", text)

    def test_short_history_is_marked_degraded(self):
        def opener(request, timeout, encoding):
            return history_payload(1) if "kline" in request.full_url else _quote_payload()

        outcome = analyze_symbol(
            SYMBOL, BoundedMarketDataProvider(BoundedUrllibProvider(opener=opener))
        )
        self.assertEqual(outcome.quality.level, "degraded_history")
        self.assertTrue(outcome.degraded)

    def test_source_provenance_survives_shipping_adapter_and_service(self):
        def opener(request, timeout, encoding):
            return history_payload() if "kline" in request.full_url else _quote_payload()

        outcome = analyze_symbol(
            SYMBOL, BoundedMarketDataProvider(BoundedUrllibProvider(opener=opener))
        )
        self.assertTrue(outcome.quality.provenance)
        self.assertEqual(outcome.quality.provenance[1].adjustment, "前复权请求")
        self.assertIsNotNone(outcome.quality.provenance[0].fetched_at)
        result = build_analysis_result(outcome.measurement, decide(outcome.measurement, 4))
        self.assertEqual(result.data_note, outcome.result.data_note)
        for rendered in (
            build_detail_text(result),
            format_results_as_csv([result]),
            format_results_for_clipboard([result]),
        ):
            self.assertIn("东方财富", rendered)
            self.assertIn("不代表交易所报价时间", rendered)


class QtLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def drain_events(self):
        for _ in range(5):
            self.app.processEvents()

    def test_disabling_rule_during_poll_discards_that_late_alert(self):
        entered, release = Event(), Event()
        rule = AlertRule("sh600000", "price", ">=", 1.0)

        class Provider:
            def fetch_quote(self, symbol):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("audit barrier timeout")
                return fake_quote(symbol)

            def fetch_history(self, symbol):
                return []

        controller = AlertController(Provider())
        received = []
        controller.alerts_triggered.connect(received.extend)
        try:
            controller.set_rules([rule])
            controller.start(60000)
            self.assertTrue(entered.wait(3))
            controller.set_rules([replace(rule, enabled=False)])
            release.set()
            self.assertTrue(controller._pool.waitForDone(3000))
            self.drain_events()
            self.assertEqual(received, [])
        finally:
            release.set()
            controller.shutdown()
            self.drain_events()

    def test_cancelled_final_response_reaches_gui_as_cancelled(self):
        entered, release = Event(), Event()

        def opener(request, timeout, encoding):
            if "kline" in request.full_url:
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("audit barrier timeout")
                return history_payload()
            return _quote_payload()

        controller = AnalysisController(
            BoundedMarketDataProvider(BoundedUrllibProvider(opener=opener))
        )
        results, reports = [], []
        controller.symbol_analyzed.connect(results.append)
        controller.batch_finished.connect(reports.append)
        try:
            controller.start("600000")
            self.assertTrue(entered.wait(3))
            controller.cancel()
            release.set()
            self.assertTrue(controller._pool.waitForDone(3000))
            self.drain_events()
            self.assertEqual(len(reports), 1)
            self.assertTrue(reports[0].cancelled)
            self.assertEqual(sum(r.ok for r in results), 0)
        finally:
            release.set()
            controller.shutdown()
            self.drain_events()


class PersistenceTests(unittest.TestCase):
    def test_malformed_alert_field_cannot_abort_config_load(self):
        from pathlib import Path

        from services.store import load_config

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "malformed-config.json"
        path.write_text(
            json.dumps({"alerts": [{"code": "600000", "field": [], "op": ">=", "threshold": 10}]}),
            encoding="utf-8",
        )
        try:
            config = load_config(path)
        except Exception as exc:
            self.fail(
                f"Valid JSON with a malformed alert field escapes load_config: {type(exc).__name__}: {exc}"
            )
        self.assertEqual(config.alerts, ())
