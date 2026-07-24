"""切档重判（REQ-003 / WI-011）。

Measurement 与 L1–L5 Decision 分离：一次分析产出一个客观 `Measurement`（与档位无关），用户来回
切档时**只对这个缓存的 Measurement 重判决策，绝不联网、绝不重新测量**。

本模块就是那条重判逻辑，**框架无关**：入参只有 `Measurement` 与目标档位——签名里根本没有
provider，因此结构上不可能触发网络请求（REQ-003）。Qt 的档位控件只调用它并把返回的
`AnalysisResult` 刷进视图。
"""

from __future__ import annotations

from domain.engine import build_analysis_result
from domain.models import LEVEL_NAMES, STANDARD_LEVEL, AnalysisResult, Measurement
from domain.policy import decide


def redecide_at_level(measurement: Measurement, level: int = STANDARD_LEVEL) -> AnalysisResult:
    """按目标档位对已缓存的 Measurement 重判，返回展示用 AnalysisResult。

    不接受 provider、不发起任何 I/O：越界档位由 `decide`/`level_spec` 的既有口径回落标准档。
    """

    return build_analysis_result(measurement, decide(measurement, level))


def redecide_all_levels(measurement: Measurement) -> dict[int, AnalysisResult]:
    """一次性给出 L1–L5 全部档位的重判结果，供档位控件即时切换而无需再次重判。"""

    return {level: redecide_at_level(measurement, level) for level in LEVEL_NAMES}
