"""数据质量信封：来源 / 获取时间 / 完整度 / 新鲜度 / 降级状态（REQ-023 / REQ-026 / WI-007）。

设计取向——**向后兼容优先**：质量元数据是一个独立的 `DataQuality` 值对象（字段全带默认），
由数据层在获取时构造、可选地随结果传递，而**不**往 `Quote`/`DailyBar`/`AnalysisResult` 等既有
dataclass 里塞必填字段。后者会破坏 domain 层所有构造点与数百个现存测试；前者是纯增量。

质量等级与 `loop/architecture/DATA_QUALITY.md`「质量等级」一节严格对齐（改这里必须同步改那份
合同）。TTL 数值不在本模块硬编码——它按操作区分，权威来源是 `config.json.data_freshness`，本
模块只提供"给定 TTL 判断是否 stale"的纯逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# 从好到坏的严重度顺序，逐字对齐 DATA_QUALITY.md。
QualityLevel = Literal["complete", "degraded_history", "partial_market", "stale", "invalid"]
QUALITY_LEVELS: tuple[QualityLevel, ...] = (
    "complete",
    "degraded_history",
    "partial_market",
    "stale",
    "invalid",
)

# 不可作为可信结果使用的等级：invalid 禁止分析；partial_market 默认不得当成全市场结果
# （DATA_QUALITY.md）。stale 可看但须标注，仍属"可用"。
_NON_ACTIONABLE: frozenset[QualityLevel] = frozenset({"invalid", "partial_market"})


def is_actionable(level: QualityLevel) -> bool:
    """该质量等级的数据是否可作为可信结果参与展示/判断。"""

    return level not in _NON_ACTIONABLE


@dataclass(frozen=True)
class DataProvenance:
    """单个数据来源的溯源记录：来源、端点、在 fallback 链中的位次（0 = 首选）。"""

    source: str
    endpoint: str
    fallback_rank: int = 0


@dataclass(frozen=True)
class DataQuality:
    """随结果传递的质量信封。默认值刻意是"无附加信息的 complete"，因此把它附加到既有结果上
    不改变任何既有语义（向后兼容）。"""

    level: QualityLevel = "complete"
    fetched_at: datetime | None = None
    provenance: tuple[DataProvenance, ...] = ()
    degradations: tuple[str, ...] = field(default=())
    """降级/清洗的可见说明（REQ-023 的"降级状态"、DATA_QUALITY.md 的"任何清洗都可见"）。"""

    @property
    def is_actionable(self) -> bool:
        return is_actionable(self.level)

    def age_seconds(self, now: datetime) -> float | None:
        """距上次成功获取的秒数；无 `fetched_at` 时返回 None（不凭空判断新鲜度）。"""

        if self.fetched_at is None:
            return None
        return (now - self.fetched_at).total_seconds()

    def is_stale(self, ttl_seconds: float, now: datetime) -> bool:
        """数据年龄是否超过给定操作的 stale TTL。年龄未知时返回 False（不误报）。

        TTL 按操作区分，权威值在 `config.json.data_freshness.stale_ttl_seconds`；本方法只做
        与该 TTL 的比较，不假定任何具体数值。
        """

        age = self.age_seconds(now)
        return age is not None and age > ttl_seconds
