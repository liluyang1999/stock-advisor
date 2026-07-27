import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.models import AlertRule, AppConfig, WatchItem
from services.store import (
    _positive_or_none,
    config_path,
    config_to_dict,
    load_config,
    log_dir,
    parse_config,
    save_config,
)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = Path(self.tmp) / "config.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_defaults(self):
        self.assertEqual(load_config(self.path), AppConfig())

    def test_roundtrip_with_positions(self):
        cfg = AppConfig(
            watchlist=(WatchItem("sh600519", 1700.0, 100), WatchItem("sz000001")),
            capital=50000.0,
            level=4,
            preset="momentum_strong",
        )
        self.assertTrue(save_config(self.path, cfg))
        loaded = load_config(self.path)
        self.assertEqual(loaded.capital, 50000.0)
        self.assertEqual(loaded.level, 4)
        self.assertEqual(loaded.preset, "momentum_strong")
        self.assertEqual(len(loaded.watchlist), 2)
        self.assertEqual(loaded.watchlist[0].cost, 1700.0)
        self.assertEqual(loaded.watchlist[0].shares, 100)
        self.assertIsNone(loaded.watchlist[1].cost)

    def test_corrupt_json_returns_defaults(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_config(self.path), AppConfig())

    def test_parse_clamps_and_filters(self):
        cfg = parse_config(
            {
                "level": 9,
                "capital": -5,
                "watchlist": [
                    {"code": "600519", "cost": -1},
                    {"code": "600519"},
                    {"code": "zzz"},
                    "000001",
                ],
                "preset": "nope",
            }
        )
        self.assertEqual(cfg.level, 5)
        self.assertEqual(cfg.capital, 100000.0)
        codes = [w.code for w in cfg.watchlist]
        self.assertEqual(codes.count("sh600519"), 1)
        self.assertIn("sz000001", codes)
        self.assertEqual(len(cfg.watchlist), 2)
        self.assertIsNone(cfg.watchlist[0].cost)  # -1 被过滤
        self.assertEqual(cfg.preset, "")

    def test_parse_rejects_fractional_share_counts(self):
        cfg = parse_config(
            {
                "watchlist": [
                    {"code": "600519", "shares": "100.5"},
                    {"code": "000001", "shares": "200.0"},
                ]
            }
        )

        self.assertIsNone(cfg.watchlist[0].shares)
        self.assertEqual(cfg.watchlist[1].shares, 200)

    def test_parse_rejects_non_finite_numbers(self):
        cfg = parse_config(
            {
                "capital": "NaN",
                "level": float("inf"),
                "watchlist": [
                    {"code": "600519", "cost": "Infinity", "shares": "Infinity"},
                ],
                "alerts": [
                    {"code": "600519", "field": "price", "op": ">=", "threshold": "Infinity"},
                ],
            }
        )

        self.assertEqual(cfg.capital, 100000.0)
        self.assertEqual(cfg.level, 3)
        self.assertEqual(len(cfg.watchlist), 1)
        self.assertIsNone(cfg.watchlist[0].cost)
        self.assertIsNone(cfg.watchlist[0].shares)
        self.assertEqual(cfg.alerts, ())

    def test_load_config_with_non_finite_level_returns_defaults(self):
        self.path.write_text('{"level": Infinity}', encoding="utf-8")

        cfg = load_config(self.path)

        self.assertEqual(cfg.level, 3)

    def test_non_dict_parses_to_defaults(self):
        self.assertEqual(parse_config([1, 2, 3]), AppConfig())
        self.assertEqual(parse_config("x"), AppConfig())

    def test_save_to_unwritable_returns_false(self):
        bad = Path("Z:/nope/zz/config.json") if os.name == "nt" else Path("/proc/zz/config.json")
        self.assertFalse(save_config(bad, AppConfig()))

    def test_save_does_not_corrupt_existing_on_resave(self):
        save_config(self.path, AppConfig(capital=1.0))
        save_config(self.path, AppConfig(capital=2.0))
        self.assertEqual(load_config(self.path).capital, 2.0)

    def test_save_config_fsyncs_before_replacing_for_crash_durability(self):
        # 掉电/崩溃 durability：临时文件的数据必须在 os.replace 之前 fsync 落盘，否则崩溃后可能
        # 出现"已改名却零长/截断"的 config。durability 无法直接崩溃测，这里断言持久化契约——
        # fsync 必须先于 replace 被调用。
        order: list[str] = []
        real_fsync, real_replace = os.fsync, os.replace

        def spy_fsync(fd):
            order.append("fsync")
            return real_fsync(fd)

        def spy_replace(src, dst):
            order.append("replace")
            return real_replace(src, dst)

        with mock.patch("os.fsync", spy_fsync), mock.patch("os.replace", spy_replace):
            self.assertTrue(save_config(self.path, AppConfig(capital=1.0)))
        self.assertEqual(order, ["fsync", "replace"], "必须先 fsync 落盘再 os.replace")
        self.assertEqual(load_config(self.path).capital, 1.0)  # 内容仍正确落地

    def test_config_path_env_override(self):
        os.environ["STOCK_ADVISOR_CONFIG"] = str(self.path)
        try:
            self.assertEqual(config_path(), self.path)
        finally:
            del os.environ["STOCK_ADVISOR_CONFIG"]

    def test_runtime_data_dir_is_StockAdvisor(self):
        # 运行时数据目录名固定为 `StockAdvisor`：config.json 与 logs/ 都落在 %APPDATA%\StockAdvisor\。
        # 用临时 APPDATA 并清掉 STOCK_ADVISOR_CONFIG 覆盖，绝不读写用户真实 %APPDATA%（AGENTS.md 硬性约束）。
        prev_appdata = os.environ.get("APPDATA")
        prev_override = os.environ.pop("STOCK_ADVISOR_CONFIG", None)
        os.environ["APPDATA"] = self.tmp
        try:
            self.assertEqual(config_path(), Path(self.tmp) / "StockAdvisor" / "config.json")
            self.assertEqual(log_dir(), Path(self.tmp) / "StockAdvisor" / "logs")
        finally:
            if prev_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = prev_appdata
            if prev_override is not None:
                os.environ["STOCK_ADVISOR_CONFIG"] = prev_override

    def test_config_to_dict_roundtrips(self):
        cfg = AppConfig(watchlist=(WatchItem("sh600519", 10.0, 200),), level=2)
        self.assertEqual(parse_config(config_to_dict(cfg)), cfg)

    def test_config_to_dict_sanitizes_non_finite_numbers(self):
        cfg = AppConfig(
            watchlist=(WatchItem("sh600519", float("inf"), float("inf")),),
            capital=float("nan"),
            level=float("inf"),  # type: ignore[arg-type]
            alerts=(AlertRule("sh600519", "price", ">=", float("nan"), True),),
        )

        data = config_to_dict(cfg)

        json.dumps(data, allow_nan=False)
        reparsed = parse_config(data)
        self.assertEqual(reparsed.capital, 100000.0)
        self.assertEqual(reparsed.level, 3)
        self.assertEqual(len(reparsed.watchlist), 1)
        self.assertIsNone(reparsed.watchlist[0].cost)
        self.assertIsNone(reparsed.watchlist[0].shares)
        self.assertEqual(reparsed.alerts, ())

    def test_alerts_roundtrip(self):
        cfg = AppConfig(
            alerts=(
                AlertRule("sh600519", "price", ">=", 1700.0, True),
                AlertRule("sz000001", "change_pct", "<=", -3.0, False),
            )
        )
        self.assertTrue(save_config(self.path, cfg))
        loaded = load_config(self.path)
        self.assertEqual(len(loaded.alerts), 2)
        self.assertEqual(loaded.alerts[0].field, "price")
        self.assertFalse(loaded.alerts[1].enabled)

    def test_alert_enabled_parser_respects_string_false_values(self):
        cfg = parse_config(
            {
                "alerts": [
                    {
                        "code": "600519",
                        "field": "price",
                        "op": ">=",
                        "threshold": 100,
                        "enabled": "false",
                    },
                    {
                        "code": "000001",
                        "field": "score",
                        "op": ">=",
                        "threshold": 20,
                        "enabled": "0",
                    },
                    {
                        "code": "300750",
                        "field": "change_pct",
                        "op": ">=",
                        "threshold": 3,
                        "enabled": "yes",
                    },
                    {"code": "600000", "field": "price", "op": ">=", "threshold": 10},
                ]
            }
        )

        self.assertEqual([alert.enabled for alert in cfg.alerts], [False, False, True, True])

    def test_config_to_dict_sanitizes_alert_enabled_values(self):
        cfg = AppConfig(
            alerts=(
                AlertRule("sh600519", "price", ">=", 1700.0, "false"),  # type: ignore[arg-type]
                AlertRule("sz000001", "score", ">=", 20.0, "0"),  # type: ignore[arg-type]
            )
        )

        data = config_to_dict(cfg)

        self.assertEqual([alert["enabled"] for alert in data["alerts"]], [False, False])

    def test_alerts_invalid_filtered(self):
        cfg = parse_config(
            {
                "alerts": [
                    {"code": "600519", "field": "price", "op": ">=", "threshold": 100},
                    {"code": "600519", "field": "bogus", "op": ">=", "threshold": 100},
                    {"code": "600519", "field": "price", "op": "!!", "threshold": 100},
                    {"code": "zzz", "field": "price", "op": ">=", "threshold": 100},
                    {"code": "600519", "field": "price", "op": ">=", "threshold": "x"},
                ]
            }
        )
        self.assertEqual(len(cfg.alerts), 1)
        self.assertEqual(cfg.alerts[0].code, "sh600519")


class StoreEdgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_positive_or_none_contract(self):
        # 注：_positive_or_none 目前在 src 内无任何调用点（疑似遗留死代码）。
        # 直测锁定其契约（不可解析/非有限/非正 → None），防止将来复用时行为漂移。
        self.assertIsNone(_positive_or_none("abc"))
        self.assertIsNone(_positive_or_none(None))
        self.assertIsNone(_positive_or_none(float("nan")))
        self.assertIsNone(_positive_or_none(0))
        self.assertIsNone(_positive_or_none(-1.5))
        self.assertEqual(_positive_or_none("2.5"), 2.5)

    def test_unparseable_level_falls_back_to_standard(self):
        # level 完全不可解析（异常路径，区别于已测的非有限数路径）→ 回退标准档 3
        self.assertEqual(parse_config({"level": "abc"}).level, 3)
        self.assertEqual(parse_config({"level": None}).level, 3)

    def test_alert_enabled_accepts_loose_value_types(self):
        def rule(enabled):
            return {
                "code": "600519",
                "field": "price",
                "op": ">=",
                "threshold": 1,
                "enabled": enabled,
            }

        cfg = parse_config(
            {"alerts": [rule("maybe"), rule(2), rule(0.0), rule(None), rule(float("nan"))]}
        )

        # 未知字符串 / None / NaN → 默认启用；数值按"非零为真"
        self.assertEqual([alert.enabled for alert in cfg.alerts], [True, True, False, True, True])

    def test_watchlist_skips_non_string_non_dict_entries(self):
        cfg = parse_config({"watchlist": [123, None, ["x"], "600519"]})

        self.assertEqual([item.code for item in cfg.watchlist], ["sh600519"])

    def test_alerts_skip_non_dict_entries(self):
        cfg = parse_config({"alerts": ["x", 42, None]})

        self.assertEqual(cfg.alerts, ())

    def test_parse_config_caps_watchlist_and_alerts_at_100(self):
        codes = [f"{600000 + i}" for i in range(105)]
        cfg = parse_config(
            {
                "watchlist": codes,
                "alerts": [
                    {"code": code, "field": "price", "op": ">=", "threshold": 1} for code in codes
                ],
            }
        )

        self.assertEqual(len(cfg.watchlist), 100)
        self.assertEqual(len(cfg.alerts), 100)

    def test_config_to_dict_skips_invalid_and_duplicate_watch_items(self):
        cfg = AppConfig(watchlist=(WatchItem("zzz"), WatchItem("sh600519"), WatchItem("sh600519")))

        data = config_to_dict(cfg)

        self.assertEqual([item["code"] for item in data["watchlist"]], ["sh600519"])

    def test_config_to_dict_caps_watchlist_and_alerts_at_100(self):
        cfg = AppConfig(
            watchlist=tuple(WatchItem(f"sh{600000 + i}") for i in range(105)),
            alerts=tuple(
                AlertRule(f"sh{600000 + i}", "price", ">=", 1.0, True) for i in range(105)
            ),
        )

        data = config_to_dict(cfg)

        self.assertEqual(len(data["watchlist"]), 100)
        self.assertEqual(len(data["alerts"]), 100)

    def test_save_config_fails_cleanly_when_target_is_directory(self):
        # 目标路径被目录占位：os.replace 失败 → 返回 False，且不残留 .cfg*.tmp 临时文件
        target = Path(self.tmp) / "config.json"
        target.mkdir()

        self.assertFalse(save_config(target, AppConfig()))
        self.assertEqual(list(Path(self.tmp).glob(".cfg*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
