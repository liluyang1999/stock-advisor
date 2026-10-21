"""Canonical daily-bar calendar contract shared by parsers and calculations."""

from datetime import date

from .models import DailyBar


def chronological_history(rows: list[DailyBar]) -> list[DailyBar]:
    unique: dict[str, DailyBar] = {}
    for row in rows:
        if not isinstance(row.date, str):
            raise ValueError("历史日线日期必须是 YYYY-MM-DD")
        try:
            day = date.fromisoformat(row.date)
        except ValueError:
            raise ValueError(f"历史日线日期无效：{row.date}") from None
        if day.isoformat() != row.date:
            raise ValueError("历史日线日期必须是 YYYY-MM-DD")
        previous = unique.get(row.date)
        if previous is not None and previous != row:
            raise ValueError(f"同一交易日存在冲突数据：{row.date}")
        unique[row.date] = row
    return [unique[key] for key in sorted(unique)]
