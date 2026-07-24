"""世代守卫单元契约（RISK-005 / WI-019）。

纯逻辑、无 Qt：证明"当前世代的结果保留、上一代的迟到结果丢弃"这条判据本身正确。控制器的
线程级竞态由 test_qt_race.py 在离屏事件循环里验证；这里只钉死守卫的算术。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qt_app.workers import GenerationGuard


class GenerationGuardTests(unittest.TestCase):
    def test_starts_at_generation_zero(self):
        self.assertEqual(GenerationGuard().current, 0)

    def test_bump_increments_and_returns_new_generation(self):
        guard = GenerationGuard()
        self.assertEqual(guard.bump(), 1)
        self.assertEqual(guard.bump(), 2)
        self.assertEqual(guard.current, 2)

    def test_current_generation_is_current(self):
        guard = GenerationGuard()
        gen = guard.bump()
        self.assertTrue(guard.is_current(gen))

    def test_superseded_generation_is_not_current(self):
        guard = GenerationGuard()
        stale = guard.bump()  # 第 1 代
        guard.bump()  # 第 2 代取代之
        self.assertFalse(guard.is_current(stale))  # 迟到的第 1 代结果应丢弃

    def test_only_the_latest_generation_survives_rapid_bumps(self):
        guard = GenerationGuard()
        gens = [guard.bump() for _ in range(5)]
        self.assertTrue(guard.is_current(gens[-1]))
        for stale in gens[:-1]:
            self.assertFalse(guard.is_current(stale))

    def test_generation_zero_is_not_current_after_first_bump(self):
        # 开轮前的初始态 0 不应被误判为任何真实轮次的当前世代。
        guard = GenerationGuard()
        guard.bump()
        self.assertFalse(guard.is_current(0))


if __name__ == "__main__":
    unittest.main()
