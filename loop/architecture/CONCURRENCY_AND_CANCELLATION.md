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

### 当前实现的历史回测通道

`AnalysisController.backtests` 持有 `BacktestController`，页面只提交本批次的日线快照、标的与档位。
回测在独立的单线程 Qt 池运行，经 queued signal 回到 GUI；不持有数据源、不发网络请求。
同一时刻最多一项计算在执行、一项最新选择等待，快速换行/切档覆盖等待项。同一批次按标的与
档位缓存，最多 150 项；改本金只更新仓位。新批次和清空会重置缓存并推进回测世代，旧报告不回填。
领域的 backtest_steps 每个历史样本之间 yield，Qt worker 在迭代间检查取消令牌；同步 API 仍耗尽同一生成器返回报告。
关窗先取消所有池，再共用最多 5000 ms 等待预算。shutdown 返回是否排空；超时则保留窗口与 worker 对象、
显示正在停止并由定时器继续检查，排空后才关闭。不使用线程强杀，也不带着活动池直接析构。

个股页的“清空”还会丢弃当前分析轮已经排入 GUI 队列的进度、行与完成结果；普通“停止”仍保留
已完成的结果。快捷键服从主按钮的忙碌状态。资金流页面以提交时的代码标注报告，输入编辑不改变
在途请求的身份。上述契约由装配级回归和后台回测测试覆盖。

- 连续双击开始只产生一个活动 generation。
- A 任务晚于 B 返回，不得覆盖 B。
- 停止后 result/finished 顺序任意，最终状态一致。
- 页面/窗口销毁后 signal 不访问已删除对象。
- 监控与主分析竞争时，主分析优先，监控跳过而非并发污染。
- 配置保存失败不改变内存中的有效配置语义。
- 发射结果后修改 worker 的源 list/dict，不得改变 GUI 已接收的 DTO。
