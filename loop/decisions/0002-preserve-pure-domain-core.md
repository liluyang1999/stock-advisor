# ADR-0002：保留纯领域核心

- 状态：accepted
- 日期：2026-07-10

## 背景

ADR-0001 决定 GUI 迁移到 PySide6，迁移采用 strangler 方式逐页面推进。一旦 controller/worker adapter 开始编写，如果不提前钉死纯核心边界，工程师很容易为了图方便直接在 QObject/QWidget 里内联业务判断逻辑，或者把 `models/engine/policy/screener/backtest/alerts/compare/chart` 等模块直接改造成依赖 Qt 信号槽的类型——这正是 RISK-004（GUI 迁移把业务逻辑搬入 QWidget）描述的风险。现有 262 项非 Tk 合同全部假设核心可以在无 GUI 环境下独立运行和测试；核心一旦悄悄长出 Qt 依赖，这些合同的可复现性和 headless 测试能力就会被破坏，且很难在代码评审中逐处发现。因此需要在迁移动手前，用一条独立 ADR 把"哪些模块必须保持纯"和"Qt 只能出现在哪里"钉死为决策，而不是留给每个 PR 各自把握。

## 决策

现有 `models/engine/policy/screener/backtest/alerts/compare/chart` 等核心继续不依赖 PySide6。Qt 仅进入 bootstrap、presentation、controller 和 worker adapter。

## 理由

这保持科学计算可独立复现，最大化 262 项非 Tk 合同的复用，并降低 GUI 迁移改变算法的风险。

## 替代方案

1. **把模型对象改为 QObject，或直接在 QWidget 中内联计算（原"拒绝方案"，拒绝）**：会引入线程归属、可变状态和难测试耦合，且 QObject 的 signal/slot 生命周期会让纯函数式的黄金向量/性质测试无法在无 GUI 环境下运行。
2. **核心与 Qt 各维护一份平行实现（Tk 时期一份、Qt 时期再复制适配 Qt 类型，拒绝）**：短期内可以绕开边界问题，但两份逻辑长期分叉、需要双份验证黄金向量，维护成本和不一致风险随时间递增，也违背"最大化 262 项非 Tk 合同复用"的目标。
3. **（采用）保持核心 Qt-free，仅在 bootstrap/presentation/controller/worker adapter 引入 Qt**：见"决策"。

## 后果

正面：presentation DTO/model adapter 之外，换来清晰依赖方向、headless 测试能力，并最大化 262 项非 Tk 合同的复用（呼应"理由"）。

负面 / 成本：controller 与 worker 之间需要额外的 presentation DTO/model adapter 做转换，每新增一个 Qt 视图都要维护一层非 Qt 数据结构，短期内增加样板代码。

## 回滚

不适用；若确需 Qt 类型进入边界，必须新 ADR 且限定 adapter。停止条件：`check_core_boundaries.py` 一旦报出纯核心对非纯子包（`data`/`services`/`ui`/`qt_app`）的越界 import，必须先阻断合并，再决定是修正代码还是走新 ADR 放宽边界，不允许纯核心带着已知越界导入进入 main。

## 重访触发

若出现可证明的、纯逻辑确实需要 Qt 信号/槽能力（例如需要跨线程 progress 汇报且现有 adapter 模式已被验证不可行）的具体场景，或 `module-map.json` 目标架构层出现与当前分层明显冲突的新证据，需要重新评估本决策并另立 ADR。

## 关联

REQ-011、REQ-027、AC-003、RISK-004、WI-000、EVD-LOOP-004、ADR-0007。

