# ADR-0002：保留纯领域核心

- 状态：accepted
- 日期：2026-07-10

## 决策

现有 `models/engine/policy/screener/backtest/alerts/compare/chart` 等核心继续不依赖 PySide6。Qt 仅进入 bootstrap、presentation、controller 和 worker adapter。

## 理由

这保持科学计算可独立复现，最大化 262 项非 Tk 合同的复用，并降低 GUI 迁移改变算法的风险。

## 拒绝方案

把模型对象改为 QObject 或直接在 QWidget 中计算：会引入线程归属、可变状态和难测试耦合。

## 后果

需要 presentation DTO/model adapter，但换来清晰依赖方向和 headless 测试。

## 回滚

不适用；若确需 Qt 类型进入边界，必须新 ADR 且限定 adapter。

