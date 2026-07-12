# ADR-0003：Qt 并发与网络边界

- 状态：accepted
- 日期：2026-07-10
- 决策来源：用户要求充分利用 PySide6 能力，并经架构审计收敛

## 背景

REQ-013 要求耗时任务不阻塞 GUI，且所有 QWidget 只能在主线程更新；REQ-025 要求网络调用具备操作 deadline、有限重试、退避抖动、错误分类、限并发和取消语义。ADR-0001 决定迁移到 PySide6 后，网络访问如果继续沿用现有同步 urllib 且缺乏统一的线程归属规则，取消、页面切换或窗口销毁时的迟到结果就可能覆盖新状态（RISK-005），而 `QNetworkReply`、`QTimer`、`QNetworkAccessManager` 一旦跨线程访问又会直接触发 Qt 未定义行为。因此需要在具体 controller/worker 代码开始编写前，把网络访问的线程归属、生命周期和取消语义定死，而不是让每个功能页面各自摸索。

## 决策

目标网络适配器使用一个长寿命 `NetworkWorker(QObject)` 与专用 `QThread` 事件循环。该 worker 在线程启动后创建并拥有 `QNetworkAccessManager`；命令通过 queued signal 进入，`QNetworkReply`、deadline `QTimer` 与 manager 始终保持同一线程归属。响应受大小上限约束，复制为不可变 bytes 后交给现有纯解析函数；大 payload 解析可转交 `QThreadPool`，不得在 GUI 线程执行。

迁移期允许把现有同步 urllib/provider 作为有界 `QThreadPool/QRunnable` 适配器复用，以降低纵向切片风险；它不是最终 Qt 网络传输。两条路径都必须返回同一 port/envelope，并使用 task_id、generation、总 deadline 和协作取消。GUI 线程只处理轻量状态与视图更新。

生命周期合同：

- manager 只在目标线程内创建，存在活动 reply 时不得 moveToThread。
- reply 完成、错误或取消后统一 `deleteLater()`；不得跨线程持有 reply。
- 关闭时先停止接收新命令，abort/取消活动请求，再 `thread.quit()` 并在有限 deadline 内 `wait()`。
- 迟到 signal 必须经 generation 丢弃；任何 QWidget 只能在 GUI 主线程访问。
- 禁止忽略 TLS 错误、无限重试、`QThread.terminate()` 或无限等待。

## 替代方案

- QNetworkAccessManager 驻留 GUI 线程：异步 API 本身可行，但与本项目“网络通道不占用 GUI 线程”的明确隔离目标不一致。
- 只包装 urllib：迁移风险低，但放弃 Qt 原生 reply/abort/redirect/TLS 生命周期能力，不作为最终态。
- asyncio/qasync：增加运行依赖和事件循环组合复杂度。
- 继续裸 thread/Queue：可工作但不能充分利用 Qt 生命周期和 queued connection。

## 后果

正面：GUI 线程绝不被网络阻塞，也不直接持有 Qt 网络对象；统一的 task_id/generation/deadline/取消语义让迟到 signal 可判定丢弃，降低 RISK-005 的发生概率；`QNetworkReply`/manager 生命周期规则明确后，`deleteLater()`/线程 quit 顺序可被测试穷举验证。

负面 / 成本：专用网络线程与迁移期 urllib 适配器两条路径并存，增加了实现和验证的复杂度（见"风险"）；所有跨线程通信都必须走 queued signal，短期内比直接函数调用更难调试；两条路径都必须验证一致的 port/envelope，测试矩阵翻倍。

## 风险

专用网络线程增加生命周期复杂度；同步 urllib 迁移适配器仍只能在请求 timeout 后退出。必须通过 EXP-003 和 WI-009 验证线程归属、reply 清理、取消、shutdown 与 fault matrix。

## 验证

取消反馈、迟到结果、窗口销毁、重复启动、监控竞争、reply `deleteLater()`、网络线程退出和 100 次生命周期测试。

## 回滚

若专用 QThread/QNetworkAccessManager 路径在联调中被证明生命周期不可控（例如无法在 deadline 内确定性 `wait()` 退出、或 reply 清理持续泄漏），回滚到迁移期 urllib/`QThreadPool` 适配器作为唯一网络实现；两条路径共享同一 port/envelope 约定，回滚不需要改变上层 controller 收到的数据形状，且回滚后仍必须保留取消/deadline/错误分类语义，不得退回无 deadline 的裸同步调用。停止条件：EXP-003 或 WI-009 验证中一旦出现 reply 跨线程访问、`QThread.terminate()` 使用或无限等待，必须立即停止把该路径当作目标网络实现。

## 重访触发

若 Qt 版本升级改变 `QNetworkAccessManager`/`QThread` 的线程归属语义或生命周期 API，或 EXP-003/WI-009 的 100 次生命周期测试发现无法收敛的竞态，需要重新评估当前 worker 模型。

## 关联

REQ-013、REQ-025、REQ-026、AC-006、WI-009、WI-019、RISK-005。
