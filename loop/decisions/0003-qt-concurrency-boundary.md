# ADR-0003：Qt 并发与网络边界

- 状态：accepted
- 日期：2026-07-10
- 决策来源：用户要求充分利用 PySide6 能力，并经架构审计收敛

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

## 风险

专用网络线程增加生命周期复杂度；同步 urllib 迁移适配器仍只能在请求 timeout 后退出。必须通过 EXP-003 和 WI-009 验证线程归属、reply 清理、取消、shutdown 与 fault matrix。

## 验证

取消反馈、迟到结果、窗口销毁、重复启动、监控竞争、reply `deleteLater()`、网络线程退出和 100 次生命周期测试。
