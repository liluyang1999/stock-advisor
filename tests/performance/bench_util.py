"""性能基准的测量工具（WI-022 / TEST-PERF-001 / performance-budgets.json）。

只用标准库：进程 RSS 经 Windows ctypes（K32GetProcessMemoryInfo）读，不引入 psutil 依赖；计时用
`time.perf_counter`。百分位按 sample_policy 的 [50,95,99] 计。RSS 仅 Windows 可用，其它平台返回
None，调用方据此 skip（产品目标平台是 Windows）。
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

_BUDGETS = Path(__file__).resolve().parents[2] / "loop" / "quality" / "performance-budgets.json"


def load_budgets() -> dict[str, dict]:
    """按 metric 名索引 performance-budgets.json 的预算，供测试读取阈值（单一真源）。"""
    doc = json.loads(_BUDGETS.read_text(encoding="utf-8"))
    return {b["metric"]: b for b in doc["budgets"]}


def rss_mib() -> float | None:
    """当前进程 RSS（MiB）。非 Windows 返回 None。"""
    if sys.platform != "win32":
        return None
    import ctypes.wintypes as wt

    class _PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD),
            ("PageFaultCount", wt.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = wt.HANDLE  # 64 位伪句柄，restype 不设会被截断成 32 位而调用失败
    k.K32GetProcessMemoryInfo.restype = wt.BOOL
    k.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
    counters = _PMC()
    counters.cb = ctypes.sizeof(_PMC)
    if not k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return counters.WorkingSetSize / 1048576.0


def percentile(samples: list[float], pct: float) -> float:
    """样本的第 `pct` 百分位（最近秩法）。样本已按需排序。"""
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100 * (len(ordered) - 1)
    lo = int(rank)
    frac = rank - lo
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def time_ms(fn, *args, **kwargs) -> float:
    """执行 `fn` 并返回耗时（毫秒）。"""
    start = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - start) * 1000.0
