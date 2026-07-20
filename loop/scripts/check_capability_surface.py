"""G-SURFACE：断言每条面向用户的需求都真的长在装配好的界面上（REQ-027 / WI-031）。

**这道门禁存在的理由是两次真实缺陷，不是理论洁癖。** WI-029 发现 TierSelector / EvidenceView /
PositionPlanView / ComparisonView 四个部件写好、单测齐全、却从未挂进任何页面，回测更是零调用；
WI-030 又发现本金与预设从不被界面读写、条件预警连新建规则的入口都没有。两轮全绿的门禁都没拦住，
两次都靠人工追问"这个用户点得到吗"才发现——那不是可重复的工程手段。

本检查把那次追问变成机器动作，做两件单元测试结构上做不到的事：

1. **完整性**：`traceability.csv` 的每条 REQ 必须在 capability-surface.json 里恰好分类一次。
   新需求要么说出它长在界面哪里，要么写明为什么没有界面——不允许沉默略过。这一条是关键：
   只检查"清单里列的东西在不在"，等于允许下一个功能压根不进清单。
2. **可达性**：真的装配一次主窗，从窗口往下找每条能力声明的部件与控件。部件类在源码里存在不算数，
   要能从 `AppWindow` 找得到才算。

离屏运行（QT_QPA_PLATFORM=offscreen），不需要显示器。
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

LOOP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = LOOP_ROOT.parent
MANIFEST = LOOP_ROOT / "product" / "capability-surface.json"
TRACEABILITY = LOOP_ROOT / "quality" / "traceability.csv"


class SurfaceError(Exception):
    """无法诚实完成检查的输入。报告出来，绝不当成通过。"""


def declared_requirements() -> list[str]:
    with TRACEABILITY.open(encoding="utf-8") as handle:
        return [row["requirement_id"] for row in csv.DictReader(handle)]


def load_manifest() -> dict[str, Any]:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SurfaceError(f"读不到 {MANIFEST}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SurfaceError(f"{MANIFEST} 不是合法 JSON: {exc}") from exc


def check_completeness(manifest: dict[str, Any], requirements: list[str]) -> list[str]:
    """每条 REQ 恰好分类一次；多分、漏分、分类到不存在的 REQ 都报错。"""
    surfaced = [entry["requirement_id"] for entry in manifest.get("capabilities", [])]
    internal = [entry["requirement_id"] for entry in manifest.get("internal", [])]
    classified = surfaced + internal
    problems: list[str] = []

    missing = [req for req in requirements if req not in classified]
    if missing:
        problems.append(
            "这些需求没有回答「它长在界面的哪里」（要么写进 capabilities，要么在 internal 里"
            f"写明没有界面的理由）：{missing}"
        )
    unknown = [req for req in classified if req not in requirements]
    if unknown:
        problems.append(f"清单里的这些 id 在 traceability.csv 中不存在：{unknown}")
    duplicated = sorted({req for req in classified if classified.count(req) > 1})
    if duplicated:
        problems.append(f"这些需求被分类了不止一次：{duplicated}")
    return problems


def check_reachability(manifest: dict[str, Any]) -> list[str]:
    """真的装一次主窗，逐条找部件与控件。找不到就是用户点不到。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    try:
        from PySide6 import QtWidgets
    except ImportError as exc:  # pragma: no cover - 环境无 Qt 时说清楚，不静默放行
        raise SurfaceError(f"没有 PySide6，无法验证界面可达性: {exc}") from exc

    import tempfile

    # 运行期才把 tests/ 注入 sys.path，pyright 静态解析不到它——这是预期，不是缺陷。
    from test_engine import FakeProvider  # type: ignore[import-not-found]

    from stock_advisor.qt_app.app import build_app
    from stock_advisor.qt_app.settings import Settings

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        # 用临时配置：门禁绝不能读写用户真实的 %APPDATA% 配置。
        settings = Settings(Path(tmp) / "config.json")
        _app, window = build_app([], provider=FakeProvider(), settings=settings)
        try:
            # findChildren 只返回后代，不含窗口自身；外壳（MainWindow/AppWindow）本身也是一种
            # 承载面（免责声明就常驻它的状态栏），所以把窗口自己的类与基类一并算作可达类型。
            widget_types = {type(w).__name__ for w in window.findChildren(QtWidgets.QWidget)}
            widget_types |= {cls.__name__ for cls in type(window).__mro__}
            names = {
                w.accessibleName()
                for w in window.findChildren(QtWidgets.QWidget)
                if w.accessibleName()
            }
            for entry in manifest.get("capabilities", []):
                req = entry["requirement_id"]
                widget = entry.get("widget")
                if widget and widget not in widget_types:
                    problems.append(
                        f"{req}: 部件 {widget} 没有挂进装配好的主窗——{entry.get('note', '')}"
                    )
                for control in entry.get("controls", []):
                    if control not in names:
                        problems.append(f"{req}: 界面上找不到可访问名为「{control}」的控件")
        finally:
            window.deleteLater()
    return problems


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        manifest = load_manifest()
        requirements = declared_requirements()
        problems = check_completeness(manifest, requirements)
        problems += check_reachability(manifest)
    except SurfaceError as exc:
        print(f"SURFACE_ERROR {exc}", file=sys.stderr)
        return 2

    if problems:
        for problem in problems:
            print(f"SURFACE_FAIL {problem}", file=sys.stderr)
        return 1

    surfaced = len(manifest.get("capabilities", []))
    internal = len(manifest.get("internal", []))
    print(
        f"SURFACE_OK requirements={surfaced + internal} user_facing={surfaced} internal={internal}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
