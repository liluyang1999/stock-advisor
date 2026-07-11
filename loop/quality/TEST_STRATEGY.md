# 测试策略

## 测试金字塔

1. 纯函数/值对象：最大量，毫秒级、无网络/GUI。
2. Provider parser、store、workflow：固定 payload/FakeProvider。
3. Qt model/controller/worker：offscreen、受控 clock/network。
4. 页面集成与故障注入：少量、覆盖关键状态机。
5. Windows 真机/打包冒烟：最少但不可缺。

## 基线保护

- 原 449 项必须保持全绿，直到行为映射完成。
- 262 项非 Tk 合同原则上零改动继续通过。
- 187 项 Tk 合同逐项标记：`pure_preserved`、`qt_replaced`、`approved_retired`。
- 不能用“新测试总数不少于旧测试”代替行为合同追溯。

## 科学计算

- 独立手算/黄金向量，不用生产函数生成 expected。
- 边界：NaN/Inf、零/负、极大数、样本不足、乱序、重复、负 PE、缺失。
- 性质：分数范围、L3 等价、仓位非负/整手/上限、切档无网络、确定性。
- 回测：前缀访问、成本、持有期限、留出集、随机生成 100 组序列。
- 若引入 mutation 工具，核心 mutation score 最终 ≥80%。

## 网络

所有 PR 测试离线。固定响应覆盖成功、fallback、429/5xx、DNS/TLS、连接/读取 timeout、截断、HTML、字段漂移、空/过大、分页中断、取消和 deadline。

## Qt

- `QT_QPA_PLATFORM=offscreen` 做 model/widget/controller 行为。
- QAbstractItemModelTester 验证模型一致性。
- QSignalSpy/事件循环辅助验证 signals、顺序和完成。
- 独立 Windows 真机覆盖 DPI、字体、窗口居中和资源插件。
- 连续打开关闭主要页面/对话框 100 次，QObject/RSS 回归。

## 稳定性

- 核心测试重复 20 次失败率 0。
- Qt 测试重复 10 次失败率 0。
- 全发布流水线连续 5 次绿色。
- 任何 flaky 测试先登记缺陷；不得简单重跑隐藏。

