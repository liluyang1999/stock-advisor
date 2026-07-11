# 并发、线程与取消

## 任务通道

独立通道：analysis、screener、monitor、fund_flow。每个通道维护：

- `generation: int`
- `task_id: str`
- `cancel_requested: bool`
- `deadline_monotonic: float`
- `running/progress/total`
- `last_error`

## Qt 线程规则

- QWidget/QPixmap 和 UI model 更新只在 GUI 主线程。
- 一次性阻塞 I/O 任务可用 QThreadPool + QRunnable；需要事件循环/长寿命 QObject 的任务使用 worker-object + QThread。
- QThread 对象本身属于创建它的线程；不把业务 slot 直接写进 QThread 子类。
- 禁止 `terminate()`；取消在请求/标的/页边界协作检查。
- Worker 发不可变结果 envelope：task_id、generation、kind、payload、error、timing。
- “frozen dataclass”不等于深度不可变；跨线程 DTO 中的 list/dict 必须转换为 tuple/只读映射或在发射前完成防御性深拷贝，发射后源容器不得再修改。
- QNetworkAccessManager 使用专用 worker-object + QThread 事件循环；短命 QRunnable 不承载需要事件循环的 manager/reply。

## 取消语义

1. 用户点击停止后 100ms 内 UI 显示“正在停止”。
2. 未开始的队列项取消。
3. 已发请求不能安全强杀时等待当前 deadline；完成结果若 generation 过期则丢弃。
4. finally 必须发 finished，控制器恢复可交互状态。
5. 清空、切页、关闭窗口递增 generation。
6. 关闭时最多等待批准的 shutdown deadline；不得无限阻塞。

## 竞态测试

- 连续双击开始只产生一个活动 generation。
- A 任务晚于 B 返回，不得覆盖 B。
- 停止后 result/finished 顺序任意，最终状态一致。
- 页面/窗口销毁后 signal 不访问已删除对象。
- 监控与主分析竞争时，主分析优先，监控跳过而非并发污染。
- 配置保存失败不改变内存中的有效配置语义。
- 发射结果后修改 worker 的源 list/dict，不得改变 GUI 已接收的 DTO。
