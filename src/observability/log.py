"""结构化日志：stdlib `logging` + `json` 的 NDJSON 输出（REQ-023/024/025/026 / WI-020）。

权威规范见 `loop/architecture/OBSERVABILITY.md`；本模块是它的落地：

- **两个 sink 同一 Formatter**：stderr（阈值 WARNING，交互式可见）与可选的 RotatingFileHandler
  （阈值 INFO，无控制台 GUI EXE 下唯一持久诊断 sink），共用 `JsonLinesFormatter`，禁止字段漂移。
- **一行一条 JSON**：标准字段 `timestamp/level/logger/message` + 出现的任务字段（`operation/
  source/error_class/degraded/cancelled/...`）。
- **不记录敏感 payload**：调用方只传安全字段；Formatter 只吐已知字段，不反射整个 record，天然不泄漏
  原始行情 payload、完整自选/持仓或凭据（OBSERVABILITY.md 的硬约束）。

`error_class` 取值固定为 7 类（network/parse/validation/persistence/gui/packaging/unknown），是
故障矩阵（NETWORK_RESILIENCE.md）与数据质量（DATA_QUALITY.md）错误归类的唯一真源。

放在 `observability/`（而非 domain 核心）：日志是 I/O 副作用，核心保持纯净（不 import logging）。
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

# 每条任务事件可携带的结构化字段（缺省不出现）。与 OBSERVABILITY.md「结构化格式」一节逐一对应。
TASK_FIELDS: tuple[str, ...] = (
    "correlation_id",
    "task_id",
    "generation",
    "operation",
    "source",
    "attempt",
    "duration_ms",
    "outcome",
    "error_class",
    "degraded",
    "cancelled",
)

_MAX_BYTES = 5_242_880  # 5 MiB
_BACKUP_COUNT = 5
_ROOT_NAME = "stock_advisor"


class JsonLinesFormatter(logging.Formatter):
    """把一条 LogRecord 渲染成一行 JSON（NDJSON）。两个 sink 共用同一实例，保证内容一致。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .astimezone()
            .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # 只吐显式声明的任务字段——不反射整个 record，避免把敏感 extra 或框架内部属性带出去。
        for field in TASK_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            # 未捕获异常归 unknown（除非调用方已显式给了 error_class）；异常文本可诊断但不含 payload。
            payload.setdefault("error_class", "unknown")
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str = _ROOT_NAME) -> logging.Logger:
    """取一个挂在 `stock_advisor` 根下的 logger。名称约定 `<子系统>`。"""
    return logging.getLogger(name if name.startswith(_ROOT_NAME) else f"{_ROOT_NAME}.{name}")


def configure_logging(log_dir: Path | None = None, *, level: int = logging.INFO) -> logging.Logger:
    """配置 `stock_advisor` 根 logger 的两个 handler（幂等：重复调用不叠加 handler）。

    - stderr handler 阈值 WARNING（交互式控制台不被 INFO 淹没）。
    - 传入 `log_dir` 时加 RotatingFileHandler，阈值 INFO（保留完整诊断轨迹），5 MiB × 5 轮转。

    两个 handler 阈值不同但共享同一 root logger 与同一 Formatter；差异只在 handler 级别。
    """
    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(level)
    root.propagate = False  # 不冒泡到 Python 根 logger，避免和宿主的默认 handler 重复输出
    formatter = JsonLinesFormatter()

    # 幂等：先清掉本模块加过的 handler（用标记识别），再按当前配置重建。
    for handler in [h for h in root.handlers if getattr(h, "_sa_managed", False)]:
        root.removeHandler(handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    stderr_handler._sa_managed = True  # type: ignore[attr-defined]
    root.addHandler(stderr_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler._sa_managed = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)

    return root


def task_extra(**fields: object) -> dict[str, object]:
    """构造只含合法任务字段的 `extra` dict（供 `logger.info(msg, extra=task_extra(...))` 用）。

    非法字段名直接报错，防止把敏感/未登记字段悄悄塞进日志；`None` 值剔除（视为"未提供"）。
    """
    unknown = set(fields) - set(TASK_FIELDS)
    if unknown:
        raise ValueError(f"未登记的日志任务字段：{sorted(unknown)}（合法字段见 TASK_FIELDS）")
    return {k: v for k, v in fields.items() if v is not None}
