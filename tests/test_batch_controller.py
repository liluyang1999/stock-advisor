"""批量分析编排契约（REQ-001/010/013 / WI-010 / TEST-QT-AN-001 的框架无关半）。

WI-010 DoD：最多 30 只 A 股代码经异步控制器规范化/去重/校验/分析，**单只失败不终止批量**，
GUI 不阻塞。这里测的是**编排逻辑**——规范化→去重→逐只分析→单只失败隔离→协作取消——它必须
框架无关、可离线确定性测试；Qt 只负责把每只提交到 QThreadPool 并用信号回主线程（另测）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import FakeProvider

from ports import ManualCancel
from services.batch import BatchProgress, run_batch_analysis


class ParseAndBatchTests(unittest.TestCase):
    def test_normalizes_dedups_and_analyzes_each_symbol(self):
        # 输入含重复与不同分隔符；去重后逐只分析。
        report = run_batch_analysis("600519, 600519  000001", FakeProvider())
        self.assertEqual(report.total, 2)  # 600519 去重
        self.assertEqual(len(report.outcomes), 2)
        self.assertTrue(all(o.ok for o in report.outcomes))

    def test_rejects_more_than_30_symbols(self):
        many = " ".join(f"60{i:04d}" for i in range(31))
        report = run_batch_analysis(many, FakeProvider())
        self.assertTrue(report.input_error)  # 超上限是输入错误，整批不启动
        self.assertEqual(report.outcomes, [])

    def test_empty_input_is_an_input_error(self):
        report = run_batch_analysis("   ", FakeProvider())
        self.assertTrue(report.input_error)

    def test_a_single_symbol_failure_never_aborts_the_batch(self):
        # REQ-010 的核心：600519 失败，000001/600000 仍必须被分析并出结果。
        provider = FakeProvider(fail_codes={"600519"})
        report = run_batch_analysis("600519 000001 600000", provider)
        self.assertEqual(report.total, 3)
        self.assertEqual(len(report.outcomes), 3)  # 三只都有 outcome
        by_ok = {o.symbol.normalized: o.ok for o in report.outcomes}
        self.assertFalse(any(v for k, v in by_ok.items() if "600519" in k))  # 失败的那只 not ok
        self.assertTrue(all(v for k, v in by_ok.items() if "600519" not in k))  # 其余都 ok
        self.assertEqual(report.failure_count, 1)
        self.assertEqual(report.success_count, 2)

    def test_progress_is_reported_per_symbol(self):
        seen: list[BatchProgress] = []
        run_batch_analysis("600519 000001 600000", FakeProvider(), on_progress=seen.append)
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[-1].done, 3)
        self.assertEqual(seen[-1].total, 3)
        self.assertEqual([p.done for p in seen], [1, 2, 3])  # 单调递增


class CancellationTests(unittest.TestCase):
    def test_cancellation_stops_the_batch_early_and_is_reported(self):
        # REQ-010：用户可安全停止任务。取消后不再分析剩余 symbol。
        cancel = ManualCancel()
        provider = FakeProvider()

        def cancel_after_first(progress):
            if progress.done == 1:
                cancel.cancel()

        report = run_batch_analysis(
            "600519 000001 600000 600036",
            provider,
            cancel_token=cancel,
            on_progress=cancel_after_first,
        )
        self.assertTrue(report.cancelled)
        self.assertLess(len(report.outcomes), 4)  # 未跑完全部
        self.assertGreaterEqual(len(report.outcomes), 1)  # 至少跑了取消前的
        self.assertLess(len(provider.calls), 4)  # provider 未被全部调用

    def test_cancel_before_start_yields_no_outcomes(self):
        cancel = ManualCancel()
        cancel.cancel()
        report = run_batch_analysis("600519 000001", FakeProvider(), cancel_token=cancel)
        self.assertTrue(report.cancelled)
        self.assertEqual(report.outcomes, [])


if __name__ == "__main__":
    unittest.main()
