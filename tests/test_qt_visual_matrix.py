"""视觉/DPI 矩阵：无裁剪 + 字体 token 合规 + 截图矩阵采集（REQ-016/018 / WI-021 / TEST-VIS-002）。

DoD 的可度量判据是「零关键裁剪、零字体 token 违规」。这里离屏把每个功能页放进从设计最小窗
（tokens.window_minimum_dip=1000×680）到更大分辨率的一组窗口尺寸里，断言：

1. **无裁剪**：页面的 minimumSizeHint 在每个尺寸内都放得下——布局不会把内容挤出窗口。
2. **字体 token 合规**：应用级字体族取自 tokens（微软雅黑契约），不是 Qt 默认字体。
3. **截图矩阵**：每个 页×尺寸 grab 一张 PNG 落到 build/screenshots/，作为 TEST-VIS-002 的产物。

真·多 DPI 像素缩放矩阵（QT_SCALE_FACTOR 逐档、跨进程）与对照设计稿的像素级视觉复核，是 CI/人工
的 V4 环节；本测试覆盖其可自动化的结构判据并产出截图供复核。
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtWidgets, qt_app, requires_qt
from test_engine import FakeProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SHOTS = PROJECT_ROOT / "build" / "screenshots"

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.alert_controller import AlertController
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController
    from stock_advisor.qt_app.controllers.fund_flow_controller import FundFlowController
    from stock_advisor.qt_app.controllers.screener_controller import ScreenerController
    from stock_advisor.qt_app.main_window import build_application
    from stock_advisor.qt_app.pages.alerts_page import AlertsPage
    from stock_advisor.qt_app.pages.evidence_page import EvidencePage
    from stock_advisor.qt_app.pages.individual_page import IndividualPage
    from stock_advisor.qt_app.pages.screener_page import ScreenerPage

# 设计最小窗（tokens.window_minimum_dip）+ 两档更大分辨率，模拟 DPI/分辨率放大后的布局分配。
_SIZES = [(1000, 680), (1280, 800), (1536, 960)]


def _page_factories():
    return {
        "individual": lambda: IndividualPage(AnalysisController(FakeProvider())),
        "evidence": lambda: EvidencePage(FundFlowController(FakeProvider())),
        "screener": lambda: ScreenerPage(ScreenerController(FakeProvider())),
        "alerts": lambda: AlertsPage(AlertController(FakeProvider())),
    }


@requires_qt
class VisualMatrixTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()
        _SHOTS.mkdir(parents=True, exist_ok=True)

    def _host(self, page, size):
        host = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page)
        host.resize(*size)
        host.show()
        self.app.processEvents()
        self.addCleanup(host.deleteLater)
        return host

    def test_no_page_clips_at_any_target_size(self):
        for name, factory in _page_factories().items():
            for width, height in _SIZES:
                with self.subTest(page=name, size=f"{width}x{height}"):
                    page = factory()
                    self._host(page, (width, height))
                    hint = page.minimumSizeHint()
                    # 无裁剪：页面最小尺寸在目标窗内放得下（负值/未定义视为无约束，跳过）。
                    if hint.width() > 0:
                        self.assertLessEqual(hint.width(), width, f"{name} 宽度裁剪")
                    if hint.height() > 0:
                        self.assertLessEqual(hint.height(), height, f"{name} 高度裁剪")

    def test_application_font_comes_from_tokens(self):
        app, window = build_application([])
        self.addCleanup(window.deleteLater)
        tokens = json.loads(
            (PROJECT_ROOT / "loop" / "product" / "tokens.json").read_text(encoding="utf-8")
        )
        want = tokens["font_families"][0]
        # 字体 token 合规：应用级字体族就是 tokens 的字体（无 token 违规）。缺字体时字体契约会
        # 记录回退，故这里断言"请求的就是 token 字体"——用应用字体族与 token 一致来证明。
        self.assertEqual(app.font().family(), want)

    def test_captures_the_full_screenshot_matrix(self):
        captured = 0
        for name, factory in _page_factories().items():
            for width, height in _SIZES:
                page = factory()
                self._host(page, (width, height))
                path = _SHOTS / f"{name}_{width}x{height}.png"
                self.assertTrue(page.grab().save(str(path)), f"截图保存失败：{path}")
                self.assertGreater(path.stat().st_size, 0)
                captured += 1
        self.assertEqual(captured, len(_page_factories()) * len(_SIZES))  # 4 页 × 3 尺寸 = 12 张


if __name__ == "__main__":
    unittest.main()
