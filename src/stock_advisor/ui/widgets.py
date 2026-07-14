"""Shared Tk widgets."""

from __future__ import annotations

from tkinter import Toplevel
from typing import Any


class StatefulToplevel(Toplevel):
    """A ``tk.Toplevel`` that carries dialog-scoped state assigned by the dialog builder and
    read by its refresh callbacks. Declaring the attributes here lets those dynamic
    assignments type-check; each dialog uses only the subset relevant to it."""

    _alert_summary_metrics: Any
    _alert_monitor_button: Any
    _alert_primary_buttons: Any
    _alert_actions_menu: Any
    _alert_field_combobox: Any
    _watchlist_summary_metrics: Any
    _watchlist_primary_buttons: Any
    _watchlist_actions_menu: Any
    _comparison_summary_metrics: Any
    _info_nav_buttons: Any
    _info_nav_frame: Any
    _info_text: Any
