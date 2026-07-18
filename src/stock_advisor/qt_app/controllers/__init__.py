"""Qt 控制器：把框架无关的编排（services/*）接到 Qt 线程模型与信号（ADR-0003）。

控制器持有 provider 与业务编排，把耗时工作提交到 `QThreadPool`，并用信号把进度/结果/完成
经 queued connection 送回 GUI 线程。页面（qt_app/pages/*）只连接这些信号更新视图，绝不自己碰
线程或阻塞调用。
"""
