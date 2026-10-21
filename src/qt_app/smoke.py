"""Bounded, offline startup check of the real assembled Qt application."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6 import QtCore

from .app import build_app


def run_smoke() -> int:
    config = os.environ.get("STOCK_ADVISOR_CONFIG")
    if not config or not Path(config).is_absolute():
        print(
            "GUI_SMOKE_REFUSED requires an absolute isolated STOCK_ADVISOR_CONFIG", file=sys.stderr
        )
        return 2
    app, window = build_app([])
    window.show()
    errors: list[str] = []

    def inspect_and_close() -> None:
        try:
            if not window.isVisible() or window.tabs.count() != 5:
                raise RuntimeError("The complete five-page application is not visible")
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                page = window.tabs.currentWidget()
                if page is None or not page.isVisible() or page.width() <= 0 or page.height() <= 0:
                    raise RuntimeError(f"Page {index} did not render")
            window.tabs.setCurrentIndex(0)
        except Exception as exc:
            errors.append(str(exc))
        finally:
            window.close()
            app.exit(1 if errors else 0)

    QtCore.QTimer.singleShot(250, inspect_and_close)
    code = app.exec()
    window.deleteLater()
    app.processEvents()
    if errors:
        print("GUI_SMOKE_FAILED " + "; ".join(errors), file=sys.stderr)
        return 1
    if code == 0 and sys.stdout is not None:
        print("GUI_SMOKE_OK pages=5 native_event_loop=True clean_shutdown=True")
    return code
