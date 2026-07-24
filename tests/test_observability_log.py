"""结构化日志契约（OBSERVABILITY.md / WI-020）。

钉死 NDJSON 格式、任务字段、无敏感字段泄漏、双 sink 阈值、handler 幂等——这些是可观测性的硬约束。
"""

import io
import json
import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from observability import (
    JsonLinesFormatter,
    configure_logging,
    get_logger,
    task_extra,
)


def _format(level: int, msg: str, **extra) -> dict:
    record = logging.LogRecord("test", level, __file__, 1, msg, (), None)
    for k, v in extra.items():
        setattr(record, k, v)
    return json.loads(JsonLinesFormatter().format(record))


class JsonLinesFormatterTests(unittest.TestCase):
    def test_emits_one_line_of_valid_json(self):
        record = logging.LogRecord("stock_advisor", logging.INFO, __file__, 1, "hi", (), None)
        line = JsonLinesFormatter().format(record)
        self.assertNotIn("\n", line)  # 一条一行
        json.loads(line)  # 合法 JSON

    def test_carries_standard_fields(self):
        payload = _format(logging.WARNING, "degraded read")
        self.assertEqual(payload["level"], "WARNING")
        self.assertEqual(payload["logger"], "test")
        self.assertEqual(payload["message"], "degraded read")
        self.assertIn("timestamp", payload)

    def test_includes_task_fields_when_present(self):
        payload = _format(
            logging.WARNING, "stale", operation="fetch_quote", error_class="network", degraded=True
        )
        self.assertEqual(payload["operation"], "fetch_quote")
        self.assertEqual(payload["error_class"], "network")
        self.assertTrue(payload["degraded"])

    def test_does_not_leak_unknown_extras(self):
        # 关键无泄漏约束：非任务字段（如原始 payload）即便被塞进 record 也不得出现在输出。
        payload = _format(logging.INFO, "ok", raw_payload="SECRET", watchlist=["600519"])
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("watchlist", payload)
        self.assertNotIn("SECRET", json.dumps(payload, ensure_ascii=False))

    def test_exception_defaults_error_class_to_unknown(self):
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                "stock_advisor", logging.ERROR, __file__, 1, "crash", (), sys.exc_info()
            )
        payload = json.loads(JsonLinesFormatter().format(record))
        self.assertEqual(payload["error_class"], "unknown")
        self.assertIn("exc", payload)


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self):
        self._root = logging.getLogger("stock_advisor")
        self._saved = list(self._root.handlers)
        self._root.handlers.clear()
        self.addCleanup(
            lambda: (self._root.handlers.clear(), self._root.handlers.extend(self._saved))
        )

    def test_is_idempotent(self):
        configure_logging()
        n = len(self._root.handlers)
        configure_logging()
        self.assertEqual(len(self._root.handlers), n)  # 重复调用不叠加 handler

    def test_stderr_handler_threshold_is_warning(self):
        configure_logging()
        stderr_handlers = [h for h in self._root.handlers if isinstance(h, logging.StreamHandler)]
        self.assertTrue(stderr_handlers)
        self.assertEqual(stderr_handlers[0].level, logging.WARNING)

    def test_file_handler_added_with_info_threshold(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            configure_logging(Path(tmp) / "logs")
            file_handlers = [h for h in self._root.handlers if isinstance(h, logging.FileHandler)]
            self.assertTrue(file_handlers)
            self.assertEqual(file_handlers[0].level, logging.INFO)
            for h in file_handlers:  # 释放文件句柄，Windows 下 TemporaryDirectory 才能清理
                h.close()

    def test_info_below_stderr_threshold_is_silent_on_stderr(self):
        buffer = io.StringIO()
        stream = logging.StreamHandler(buffer)
        stream.setLevel(logging.WARNING)
        stream.setFormatter(JsonLinesFormatter())
        self._root.addHandler(stream)
        self._root.setLevel(logging.INFO)
        get_logger("net").info("task start")  # INFO < WARNING → 不落 stderr
        get_logger("net").warning("degraded")  # WARNING → 落
        lines = [x for x in buffer.getvalue().splitlines() if x]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["message"], "degraded")


class TaskExtraTests(unittest.TestCase):
    def test_rejects_unregistered_fields(self):
        with self.assertRaises(ValueError):
            task_extra(operation="x", raw_payload="secret")  # raw_payload 非法

    def test_drops_none_values(self):
        extra = task_extra(operation="fetch", source=None, degraded=True)
        self.assertEqual(extra, {"operation": "fetch", "degraded": True})


if __name__ == "__main__":
    unittest.main()
